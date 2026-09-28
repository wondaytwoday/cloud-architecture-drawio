#!/usr/bin/env node
// Render the actual mxGraph model using draw.io's viewer, never an imitation.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const [input, output, viewer] = process.argv.slice(2);
if (!input || !output || !viewer) {
  console.error('Usage: node render.cjs input.drawio output.png /path/to/viewer-static.min.js');
  process.exit(1);
}
(async () => {
  const xml = fs.readFileSync(input, 'utf8');
  const reportPath=input.replace(/\.drawio$/,'.report.json');
  const expected=fs.existsSync(reportPath) ? JSON.parse(fs.readFileSync(reportPath,'utf8')) : null;
  const browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH}: {})});
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1600},deviceScaleFactor:1});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // All assets are embedded. Do not send architecture data to remote services.
    await page.route('**/*', route => route.abort());
    await page.setContent('<!doctype html><html><head><style>html,body{margin:0;background:white}#graph{position:relative;overflow:hidden}</style></head><body><div id="graph"></div></body></html>');
    await page.evaluate(() => {window.mxLoadResources=false; window.mxLoadStylesheets=false; window.urlParams={};});
    await page.addScriptTag({content:fs.readFileSync(viewer,'utf8')});
    const result = await page.evaluate(xml => {
      const doc=mxUtils.parseXml(xml);
      const model=doc.querySelector('mxGraphModel');
      if (!model) throw new Error('Expected uncompressed mxGraphModel');
      const width=Number(model.getAttribute('pageWidth')),height=Number(model.getAttribute('pageHeight'));
      const container=document.getElementById('graph');
      container.style.width=width+'px'; container.style.height=height+'px';
      const graph=new Graph(container); graph.setEnabled(false); graph.setHtmlLabels(false);
      new mxCodec(doc).decode(model,graph.getModel()); graph.refresh();
      window.renderGraph=graph;
      const unknown=[];
      for (const c of Object.values(graph.model.cells)) {
        if (c.vertex && c.id.startsWith('__icon_')) {
          const state=graph.view.getState(c);
          if (!state?.shape?.node || !state.shape.node.querySelector('path,image,rect,ellipse') || (String(state.style.shape).startsWith('stencil(') && !state.shape.stencil)) unknown.push(c.id);
        }
      }
      return {width,height,cells:Object.keys(graph.model.cells).length,unknownIcons:unknown};
    },xml);
    await page.setViewportSize({width:result.width,height:result.height});
    result.brokenImages=await page.evaluate(async () => {
      await document.fonts.ready;
      const broken=[];
      await Promise.all([...document.querySelectorAll('image')].map(el=>new Promise(resolve=>{
        const i=new Image(); i.onload=resolve; i.onerror=()=>{broken.push(el.closest('[data-cell-id]')?.getAttribute('data-cell-id') || 'embedded image');resolve();};
        i.src=el.getAttribute('href')||el.getAttribute('xlink:href');
      })));
      return broken;
    });
    result.geometry=await page.evaluate(expected=>{
      const g=window.renderGraph,mismatches=[];let checkedRoutes=0,checkedLabels=0,jumpMarkers=0;
      for(const c of Object.values(g.model.cells).filter(c=>c.edge)) {
        const state=g.view.getState(c);
        jumpMarkers+=(state.routedPoints||[]).filter(p=>p.type===1).length;
        if(!expected?.routes?.[c.id]) continue;
        checkedRoutes++;
        const actual=state.absolutePoints,wanted=expected.routes[c.id];
        if(actual.length!==wanted.length || actual.some((p,i)=>!wanted[i] || Math.abs(p.x-wanted[i][0])>.05 || Math.abs(p.y-wanted[i][1])>.05)) mismatches.push(c.id+': route geometry');
      }
      for(const [eid,label] of Object.entries(expected?.labels||{})) {
        checkedLabels++;
        const c=g.model.getCell('__label_'+eid),s=g.view.getState(c),r=label.rect;
        // mxGraph rounds the along-edge anchor to the nearest screen pixel.
        if(!s || !c.parent?.edge || !c.geometry.relative || [s.x,s.y,s.width,s.height].some((v,i)=>Math.abs(v-r[i])>.51)) mismatches.push({id:eid,type:'label geometry or attachment',actual:s?[s.x,s.y,s.width,s.height]:null,expected:r});
      }
      return {checkedRoutes,checkedLabels,jumpMarkers,mismatches};
    },expected);
    fs.mkdirSync(path.dirname(output),{recursive:true});
    await page.screenshot({path:output,fullPage:true});
    const svg=await page.evaluate(() => {
      const svg=document.querySelector('#graph svg').cloneNode(true);
      svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
      svg.setAttribute('width',document.getElementById('graph').style.width);
      svg.setAttribute('height',document.getElementById('graph').style.height);
      return new XMLSerializer().serializeToString(svg);
    });
    fs.writeFileSync(output.replace(/\.png$/,'.svg'),svg);
    result.editability=await page.evaluate(() => {
      const g=window.renderGraph;
      const all=Object.values(g.model.cells);
      const node=all.find(c=>c.vertex && c.edges?.length && c.children?.some(k=>k.id.startsWith('__icon_'))) || all.find(c=>c.vertex && c.children?.some(k=>k.id.startsWith('__icon_')));
      if(!node) throw new Error('No editable resource group');
      const before=node.geometry.clone(); const changed=before.clone(); changed.x+=10;
      g.model.setGeometry(node,changed);
      const moved=node.geometry.x===before.x+10;
      g.model.setGeometry(node,before);
      // Translate one labeled connector and both endpoints, then restore. Its
      // relative child caption must follow native mxGraph geometry, not float.
      const edge=all.find(c=>c.edge && c.children?.some(k=>k.id.startsWith('__label_')));
      let labelFollow=null;
      if(edge) {
        const label=edge.children.find(k=>k.id.startsWith('__label_'));
        g.refresh();const labelBefore=g.view.getState(label);const xy=[labelBefore.x,labelBefore.y];
        const cells=[edge.source,edge.target,edge],saved=cells.map(c=>c.geometry.clone());
        g.model.beginUpdate();
        try {
          for(let i=0;i<cells.length;i++) {
            const geo=saved[i].clone();
            if(cells[i].edge) geo.points=geo.points?.map(p=>new mxPoint(p.x+20,p.y+10));
            else {geo.x+=20;geo.y+=10;}
            g.model.setGeometry(cells[i],geo);
          }
        } finally {g.model.endUpdate();}
        g.refresh();const after=g.view.getState(label);
        labelFollow=Math.abs(after.x-xy[0]-20)<.05 && Math.abs(after.y-xy[1]-10)<.05;
        g.model.beginUpdate();try {cells.forEach((c,i)=>g.model.setGeometry(c,saved[i]));} finally {g.model.endUpdate();}
        g.refresh();
      }
      const codec=new mxCodec(); const encoded=codec.encode(g.model);
      const roundTripDoc=mxUtils.parseXml(mxUtils.getXml(encoded));
      const decoded=new mxGraphModel(); new mxCodec(roundTripDoc).decode(roundTripDoc.documentElement,decoded);
      const edges=Object.values(decoded.cells).filter(c=>c.edge);
      const intact=edges.every(c=>c.source && c.target);
      const labels=Object.values(decoded.cells).filter(c=>c.id.startsWith('__label_'));
      const labelsIntact=labels.every(c=>c.parent?.edge && c.geometry.relative);
      if(!moved||!intact||!labelsIntact||labelFollow===false) throw new Error('Editable round-trip or label movement failed');
      return {movedResource:node.id,restored:true,roundTripEdges:edges.length,allEdgesConnected:intact,roundTripLabels:labels.length,allLabelsAttached:labelsIntact,labelFollow};
    });
    result.pageErrors=errors;
    fs.writeFileSync(output.replace(/\.png$/,'.render.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
    if(errors.length||result.unknownIcons.length||result.brokenImages.length||result.geometry.mismatches.length) process.exitCode=1;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
