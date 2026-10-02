#!/usr/bin/env node
// Render the actual mxGraph model using draw.io's viewer, never an imitation.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const USAGE = 'Usage: node render.cjs input.drawio output.png [viewer-static.min.js] [--report report.json | --no-report] [--page N] [--embed]\n'
  + 'The viewer path may come from $DRAWIO_VIEWER. --no-report renders a manually edited file without comparing planned geometry.';
const fail = message => { console.error(message); process.exit(1); };
const positional = [], options = {page: 1, report: undefined, embed: false};
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  const value = () => { const v = process.argv[++i]; if (v === undefined || v.startsWith('--')) fail(`${arg} needs a value\n${USAGE}`); return v; };
  if (arg === '--no-report') options.report = null;
  else if (arg === '--embed') options.embed = true;
  else if (arg === '--report') options.report = value();
  else if (arg === '--page') options.page = Number(value());
  else if (arg.startsWith('--')) fail(`Unknown option ${arg}\n${USAGE}`);
  else positional.push(arg);
}
const [input, output, viewer = process.env.DRAWIO_VIEWER] = positional;
if (!input || !output || !viewer || !Number.isInteger(options.page) || options.page < 1) fail(USAGE);
// Sibling outputs share the PNG's base name, so no extension can overwrite another output.
const out = path.parse(output);
if (out.ext.toLowerCase() !== '.png') fail(`${output}: output must be a .png file; the SVG and .render.json are written beside it`);
const svgPath = path.join(out.dir, out.name+'.svg'), renderPath = path.join(out.dir, out.name+'.render.json');
// Same rule as the compiler's Path.with_suffix('.report.json').
const inp = path.parse(input);
const reportPath = options.report === undefined ? path.join(inp.dir, inp.name+'.report.json') : options.report;
const sha256 = data => crypto.createHash('sha256').update(data).digest('hex');
const CRC = Array.from({length: 256}, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc32 = buf => { let c = 0xFFFFFFFF; for (const b of buf) c = CRC[(c ^ b) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
// draw.io reads an editable diagram from a tEXt chunk named mxfile before the image data.
function embedInPng(png, xml) {
  const type = Buffer.from('tEXt', 'latin1'), data = Buffer.from('mxfile\0'+encodeURIComponent(xml), 'latin1');
  const length = Buffer.alloc(4), crc = Buffer.alloc(4);
  length.writeUInt32BE(data.length); crc.writeUInt32BE(crc32(Buffer.concat([type, data])));
  const afterHeader = 8+4+4+13+4;
  return Buffer.concat([png.subarray(0, afterHeader), length, type, data, crc, png.subarray(afterHeader)]);
}
const source = fs.readFileSync(input);
// An old .render.json must never sit beside a PNG from a run that failed.
fs.rmSync(renderPath, {force: true});
let expected = null;
if (reportPath !== null) {
  if (!fs.existsSync(reportPath)) fail(`${reportPath}: compiler report not found, so route and label geometry cannot be compared. Rebuild, pass --report PATH, or pass --no-report for a manually edited file.`);
  expected = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  if (expected.drawio_sha256 && expected.drawio_sha256 !== sha256(source)) fail(`${reportPath}: stale report; ${input} changed after it was built (manual edit?). Rebuild from the model, or pass --no-report to check the edited file without planned geometry.`);
  // A bundle report plans each page separately.
  if (Array.isArray(expected.pages)) {
    if (!expected.pages[options.page-1]) fail(`${reportPath}: plans ${expected.pages.length} page(s), not page ${options.page}`);
    expected = expected.pages[options.page-1];
  }
}

(async () => {
  const xml = source.toString('utf8');
  let browser;
  try { browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH}: {})}); }
  catch (e) {
    // Exit 3 tells callers the renderer is unavailable here, not that the diagram failed.
    console.error(`browser could not be launched: ${String(e.message||e).split('\n')[0]}; run "playwright install chromium" or set CHROME_PATH`);
    process.exit(3);
  }
  try {
    const page = await browser.newPage({viewport:{width:1600,height:1600},deviceScaleFactor:1});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // All assets are embedded. Do not send architecture data to remote services.
    await page.route('**/*', route => route.abort());
    await page.setContent('<!doctype html><html><head><style>html,body{margin:0;background:white}#graph{position:relative;overflow:hidden}</style></head><body><div id="graph"></div></body></html>');
    await page.evaluate(() => {window.mxLoadResources=false; window.mxLoadStylesheets=false; window.urlParams={};});
    await page.addScriptTag({content:fs.readFileSync(viewer,'utf8')});
    const result = await page.evaluate(({xml, pageNumber}) => {
      const doc=mxUtils.parseXml(xml);
      const diagrams=[...doc.getElementsByTagName('diagram')];
      const pages=diagrams.length || 1;
      if (pageNumber>pages) throw new Error(`Page ${pageNumber} requested, but the file has ${pages} page(s)`);
      let model=diagrams.length ? diagrams[pageNumber-1].getElementsByTagName('mxGraphModel')[0] : doc.getElementsByTagName('mxGraphModel')[0];
      if (!model && diagrams.length) {
        const text=diagrams[pageNumber-1].textContent.trim();
        if (text) model=mxUtils.parseXml(Graph.decompress(text)).documentElement;
      }
      if (!model || model.nodeName!=='mxGraphModel') throw new Error('No mxGraphModel found; is this a draw.io file?');
      // Decode one page on its own: every page reuses cell IDs such as 0 and 1.
      const pageDoc=mxUtils.parseXml(mxUtils.getXml(model)); model=pageDoc.documentElement;
      const container=document.getElementById('graph');
      const background=model.getAttribute('background');
      const fill=background && background!=='none' ? background : '#FFFFFF';
      container.style.background=fill;
      const graph=new Graph(container); graph.setEnabled(false); graph.setHtmlLabels(false);
      new mxCodec(pageDoc).decode(model,graph.getModel()); graph.refresh();
      window.renderGraph=graph;
      // Without a page size, fall back to draw.io's default page grown to the content.
      const bounds=graph.getGraphBounds();
      // Browsers size viewports in whole pixels.
      const width=Math.ceil(Number(model.getAttribute('pageWidth'))||Math.max(850,bounds.x+bounds.width+10));
      const height=Math.ceil(Number(model.getAttribute('pageHeight'))||Math.max(1100,bounds.y+bounds.height+10));
      container.style.width=width+'px'; container.style.height=height+'px';
      graph.refresh();
      const cells=Object.values(graph.model.cells);
      // Content beyond the page would be cut from the PNG and SVG without a trace.
      const offPage=[];
      for (const c of cells) {
        const state=graph.view.getState(c);
        if (!state || !(c.vertex||c.edge)) continue;
        const pts=c.edge ? (state.absolutePoints||[]).filter(Boolean) : [{x:state.x,y:state.y},{x:state.x+state.width,y:state.y+state.height}];
        if (pts.some(p=>p.x<-1||p.y<-1||p.x>width+1||p.y>height+1)) offPage.push(c.id);
      }
      // Icons must resolve offline: embedded stencils, registered shapes or stencils.
      const resolves=name=>{
        if (mxCellRenderer.defaultShapes[name]) return true;
        try { return Boolean(mxStencilRegistry.getStencil(name)); } catch { return false; }
      };
      const unknown=[];
      for (const c of cells) {
        if (!c.vertex) continue;
        const state=graph.view.getState(c),shape=String(state?.style?.shape||'');
        const broken=c.id.startsWith('__icon_') && (!state?.shape?.node || !state.shape.node.querySelector('path,image,rect,ellipse'));
        const missingStencil=shape.startsWith('stencil(') ? !state.shape.stencil : (shape.startsWith('mxgraph.') && !resolves(shape));
        const missingResIcon=state?.style?.resIcon && !resolves(String(state.style.resIcon));
        if (broken||missingStencil||missingResIcon) unknown.push(c.id);
      }
      return {page:pageNumber,pages,width,height,background:fill,cells:cells.length,edges:cells.filter(c=>c.edge).length,unknownIcons:unknown,offPage};
    },{xml,pageNumber:options.page});
    await page.setViewportSize({width:result.width,height:result.height});
    result.brokenImages=await page.evaluate(async () => {
      await document.fonts.ready;
      const g=window.renderGraph,broken=[];
      await Promise.all(Object.values(g.model.cells).flatMap(c=>{
        const node=g.view.getState(c)?.shape?.node;
        return node ? [...node.querySelectorAll('image')].map(el=>new Promise(resolve=>{
          const i=new Image(); i.onload=resolve; i.onerror=()=>{broken.push(c.id);resolve();};
          i.src=el.getAttribute('href')||el.getAttribute('xlink:href');
        })) : [];
      }));
      return broken;
    });
    // A label clipped by overflow=hidden can look complete, so measure the box.
    result.textOverflow=await page.evaluate(() => {
      const g=window.renderGraph,clipped=[];
      for (const c of Object.values(g.model.cells)) {
        const state=g.view.getState(c),node=state?.text?.node;
        if (!node) continue;
        for (const fo of node.querySelectorAll('foreignObject')) {
          const box=fo.querySelector('div > div'),text=box?.firstElementChild;
          if (!box) continue;
          const over=box.scrollHeight>box.clientHeight+0.5 || box.scrollWidth>box.clientWidth+1;
          // Captions, legend entries and boundary titles are not clipped; they must not
          // wrap beyond their explicit lines. offsetHeight ignores label rotation.
          const lineHeight=Number(state.style.fontSize||11)*1.2;
          const lines=(String(c.value||'').match(/\n|<br\s*\/?>/gi)||[]).length+1;
          const oneLine=c.id.startsWith('__label_') || c.id.startsWith('__legend_text_') || (state.style.container==1 && c.value && state.style.horizontal!=0);
          const tall=oneLine && text && text.offsetHeight>lineHeight*(lines+.5);
          if (over||tall) clipped.push({id:c.id,text:box.textContent.slice(0,60),box:[box.clientWidth,box.clientHeight],content:[box.scrollWidth,tall?text.offsetHeight:box.scrollHeight]});
        }
      }
      return clipped;
    });
    result.geometry=await page.evaluate(expected=>{
      const g=window.renderGraph,mismatches=[],markers=[];let checkedRoutes=0,checkedLabels=0;
      const edges=Object.values(g.model.cells).filter(c=>c.edge);
      for(const c of edges) {
        const state=g.view.getState(c);
        for(const p of state.routedPoints||[]) if(p.type===1) markers.push([c.id,p.x,p.y]);
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
      if(expected) {
        const planned=Object.keys(expected.routes||{}).length;
        if(planned!==edges.length || checkedRoutes!==edges.length) mismatches.push(`report covers ${checkedRoutes} of ${edges.length} connectors (it plans ${planned}); rebuild or use the matching report`);
      }
      // Every planned crossing must show draw.io's jump arc on one of its two edges.
      const missingJumps=[];
      for(const crossing of expected?.quality?.crossings||[]) {
        const [x,y]=crossing.point;
        if(!markers.some(([id,mx,my])=>crossing.edges.includes(id) && Math.abs(mx-x)<1 && Math.abs(my-y)<1)) missingJumps.push(crossing);
      }
      if(missingJumps.length) mismatches.push({type:'crossing without jump arc',crossings:missingJumps});
      return {checkedRoutes,checkedLabels,jumpMarkers:markers.length,missingJumps:missingJumps.length,mismatches};
    },expected);
    fs.mkdirSync(out.dir||'.',{recursive:true});
    const shot=await page.screenshot({fullPage:true,type:'png'});
    fs.writeFileSync(output,options.embed?embedInPng(shot,xml):shot);
    const svg=await page.evaluate(({fill,embed,xml}) => {
      const svg=document.querySelector('#graph svg').cloneNode(true);
      svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
      svg.setAttribute('width',document.getElementById('graph').style.width);
      svg.setAttribute('height',document.getElementById('graph').style.height);
      // An explicit page background keeps the preview readable in dark viewers.
      const bg=document.createElementNS('http://www.w3.org/2000/svg','rect');
      bg.setAttribute('width','100%'); bg.setAttribute('height','100%'); bg.setAttribute('fill',fill);
      svg.insertBefore(bg,svg.firstChild);
      // draw.io opens an SVG with the diagram in its content attribute as editable.
      if(embed) svg.setAttribute('content',xml);
      return new XMLSerializer().serializeToString(svg);
    },{fill:result.background,embed:options.embed,xml});
    fs.writeFileSync(svgPath,svg);
    if(options.embed) {
      // Read both files back the way draw.io would, and require the exact source.
      result.embedded=await page.evaluate(({png,svg,xml}) => ({
        png: typeof Editor!=='undefined' && Editor.extractGraphModelFromPng('data:image/png;base64,'+png)===xml,
        svg: new DOMParser().parseFromString(svg,'image/svg+xml').documentElement.getAttribute('content')===xml,
      }),{png:fs.readFileSync(output).toString('base64'),svg,xml});
    }
    result.editability=await page.evaluate(() => {
      const g=window.renderGraph;
      const all=Object.values(g.model.cells);
      const node=all.find(c=>c.vertex && c.edges?.length && c.children?.some(k=>k.id.startsWith('__icon_'))) || all.find(c=>c.vertex && c.children?.some(k=>k.id.startsWith('__icon_')));
      if(!node) return {skipped:'no compiler-built resource group on this page'};
      // Free annotation arrows are legitimate; only connected edges must stay connected.
      const connected=new Set(all.filter(c=>c.edge && c.source && c.target).map(c=>c.id));
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
      const detached=edges.filter(c=>connected.has(c.id) && !(c.source && c.target)).map(c=>c.id);
      const labels=Object.values(decoded.cells).filter(c=>c.id.startsWith('__label_'));
      const loose=labels.filter(c=>!(c.parent?.edge && c.geometry.relative)).map(c=>c.id);
      const result={movedResource:node.id,restored:true,roundTripEdges:edges.length,allEdgesConnected:!detached.length,roundTripLabels:labels.length,allLabelsAttached:!loose.length,labelFollow};
      if(!moved||detached.length||loose.length||labelFollow===false) result.error=`editable round trip failed: moved=${moved}, detached edges [${detached}], loose labels [${loose}], labelFollow=${labelFollow}`;
      return result;
    });
    result.pageErrors=errors;
    result.warnings=result.editability.skipped ? [`editability not checked: ${result.editability.skipped}`] : [];
    let playwrightVersion=null;
    try {playwrightVersion=require('playwright/package.json').version;} catch {}
    result.provenance={input_sha256:sha256(source),report:reportPath,viewer_sha256:sha256(fs.readFileSync(viewer)),playwright:playwrightVersion};
    fs.writeFileSync(renderPath,JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
    const embedFailed=options.embed && !(result.embedded.png && result.embedded.svg);
    if(errors.length||result.unknownIcons.length||result.offPage.length||result.brokenImages.length||result.textOverflow.length||result.geometry.mismatches.length||result.editability.error||embedFailed) process.exitCode=1;
  } finally {await browser.close();}
})().catch(e=>{console.error(e?.stack||String(e));process.exitCode=1;});
