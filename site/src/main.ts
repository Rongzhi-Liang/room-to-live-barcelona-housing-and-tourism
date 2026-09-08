import mapboxgl, { type Map as MapboxMap, type ExpressionSpecification } from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import './style.css';
type Lang = 'en' | 'zh';
type Bilingual = {
    en: string;
    zh: string;
};
type Chapter = {
    id: string;
    title: Bilingual;
    body: Bilingual;
    eyebrow: Bilingual;
    microNote?: Bilingual;
    map: string;
    chart?: string;
    diagram?: string;
    sourceIds: string[];
};
type Feature = {
    type: 'Feature';
    id?: string | number;
    geometry: any;
    properties: Record<string, any>;
};
type Collection = {
    type: 'FeatureCollection';
    features: Feature[];
};
type Editorial = {
    objective: Bilingual;
    chapters: Chapter[];
    diagrams: any[];
    bindings?: Record<string, string | number>;
    [key: string]: any;
};
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const tr = (en: string, zh: string) => lang === 'en' ? en : zh;
const fmt = (v: unknown, d = 1) => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString(lang === 'en' ? 'en-GB' : 'zh-CN', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—';
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const mobile = () => innerWidth <= 600;
let lang: Lang = (localStorage.getItem('room-language') === 'zh' ? 'zh' : 'en');
let content: Editorial, summary: any, neighbourhoods: Collection, grid: Collection, hut: Collection, places: Collection, cityContext: Collection, sources: any[] = [];
let map: MapboxMap | undefined, ready = false, active = 0, exploring = false, exploreSaved = { index: 0, y: 0, anchorTop: 100 }, snapshot = 3, platformMode = 'count', observationMode = 'count', comparison = 'level', caseIndex = 0, scrollFrame = 0;
let baseStyle: any, mapRegistry: any = {}, selected: string | null = null, simpleMap = false, jumpTarget: number | null = null, jumpTimer = 0;
let publishedStyleUrl = '';
const usePublishedSources = import.meta.env.VITE_MAPBOX_SOURCE_MODE === 'published';
const assetURL = (path: string) => import.meta.env.BASE_URL + path;
const categories: Record<string, string> = { both: '#c74f40', tourism: '#dc9563', rent: '#8c8c8c', neither: '#353535', unavailable: '#222222' };
const themeField: Record<string, string> = { M04: 'hutIntensity', M05: 'rent2025', M06: 'rentChange', M07: 'contractIntensity', M08: 'overlapClass' };
const fetchJSON = async (path: string, timeout?: number) => { const r = await fetch(path, timeout ? { signal: AbortSignal.timeout(timeout) } : undefined); if (!r.ok)
    throw new Error(path); return r.json(); };
async function loadMapStyle() {
    const [localStyle, production] = await Promise.all([
        fetchJSON(assetURL('mapbox/base.style.json'), 6000).catch(() => null),
        usePublishedSources ? fetchJSON(assetURL('mapbox/production.json'), 2000).catch(() => null) : Promise.resolve(null)
    ]);
    const reference = production?.styleUrl?.match(/^mapbox:\/\/styles\/([\w-]+)\/([\w-]+)$/);
    if (reference) {
        try {
            const style = await fetchJSON(`https://api.mapbox.com/styles/v1/${reference[1]}/${reference[2]}?access_token=${import.meta.env.VITE_MAPBOX_TOKEN}`, 6000);
            if (style.version === 8 && Array.isArray(style.layers)) {
                publishedStyleUrl = production.styleUrl;
                return style;
            }
        } catch { /* The saved base style keeps the map available during a service interruption. */ }
    }
    publishedStyleUrl = '';
    return localStyle;
}
async function start() {
    const loading = document.querySelector('.loading-story p:last-child');
    if (loading) loading.textContent = tr('Loading the story…', '正在载入故事…');
    try {
        [content, summary, neighbourhoods, grid, hut, places, cityContext, baseStyle] = await Promise.all(['editorial.json', 'summary.json', 'neighbourhoods.geojson', 'grid.geojson', 'hut.geojson', 'qualitative.geojson', 'city-context.geojson'].map(f => fetchJSON(assetURL('data/' + f))).concat([loadMapStyle()]));
        const rawSources = await fetchJSON(assetURL('data/sources.json'));
        sources = Array.isArray(rawSources) ? rawSources : rawSources.sources ?? [];
        mapRegistry = usePublishedSources ? await fetchJSON(assetURL('mapbox/registry.json')).catch(() => ({})) : {};
        render();
        document.body.dataset.firstContentMs = String(Math.round(performance.now()));
        initMap();
    }
    catch (e) {
        $('#app').innerHTML = `<main class="loading-story"><h1>${tr('Room to Live', '住下来的空间')}</h1><p>${tr('The story could not load. Please check your connection and try again.', '故事暂未载入，请检查网络后重试。')}</p><button id="reload-story">${tr('Reload story', '重新载入')}</button></main>`;
        $('#reload-story').onclick = () => location.reload();
        console.error('Story data could not load', e);
    }
}
function paragraph(body: string) { return body.split(/\n\n/).filter(Boolean).map(p => `<p>${esc(p)}</p>`).join(''); }
function workCredit() {
    return `<footer class="work-credit" aria-label="${tr('Project credits', '作品落款')}"><div class="credit-details"><span class="credit-author">Rongzhi Liang</span><span>${tr('National University of Singapore', '新加坡国立大学（NUS）')}</span><span>DEP5118 · Community Data Gathering and Visualisation</span><span>${tr('Coursework · ITA2', '课程作业 · ITA2')}</span><time datetime="2026-09">${tr('September 2026', '2026年9月')}</time></div></footer>`;
}
function render() {
    const y = scrollY;
    const existingMap = document.getElementById('map');
    document.documentElement.lang = lang;
    document.documentElement.dataset.reduced = String(reduced());
    document.title = tr('Room to Live — Barcelona', '住下来的空间 — 巴塞罗那');
    const chapters = content.chapters;
    $('#app').innerHTML = `<a class="skip" href="#chapter-01">${tr('Read the story', '阅读故事')}</a><div id="map-fallback" hidden></div><div id="map" role="region" aria-label="${tr('Barcelona evidence map', '巴塞罗那证据地图')}"></div>
 <div class="map-shade" aria-hidden="true"></div><div class="progress" aria-hidden="true"></div><header class="topbar"><a class="wordmark" href="#chapter-01">${tr('Room to Live', '住下来的空间')}</a><nav class="nav" aria-label="${tr('Main navigation', '主导航')}"><button class="desktop-nav" data-dialog="contents">${tr('Chapters', '章节')}</button><button class="desktop-nav" id="explore-open">${tr('Explore', '探索')}</button><button class="desktop-nav" data-dialog="method">${tr('Method', '方法')}</button><button class="desktop-nav" data-dialog="sources">${tr('Sources', '来源')}</button><button class="menu-button" data-dialog="contents">${tr('Index', '目录')}</button><button class="language" id="language" aria-label="${tr('Switch to Chinese', '切换为英文')}">${tr('中文', 'EN')}</button></nav></header>
 <div class="hero-location"><span class="city">Barcelona</span><span class="coords">41°23′ N &nbsp; 2°10′ E</span></div>
 <nav class="chapter-rail" aria-label="${tr('Story chapters', '故事章节')}">${chapters.map((c, i) => `<button data-goto="${i}" aria-label="${esc(c.id + ' ' + c.title[lang])}" title="${esc(c.title[lang])}"><span class="chapter-tooltip">${c.id} ${esc(c.title[lang])}</span></button>`).join('')}</nav>
 <main id="story">${chapters.map((c, i) => `<section class="chapter ${i === 0 ? 'hero' : ''} ${[1, 5, 6, 9, 11].includes(i) ? 'right' : ''}" id="chapter-${c.id}" data-index="${i}" aria-labelledby="heading-${c.id}"><div class="copy"><p class="eyebrow"><span class="num">${c.id} / 14</span>${esc(c.eyebrow?.[lang] || tr('Barcelona · Housing', '巴塞罗那 · 住房'))}</p>${i === 0 ? `<h1 id="heading-${c.id}">${tr('Room<br>to <em>Live.</em>', '住下来的<br><em>空间。</em>')}</h1>` : `<h2 id="heading-${c.id}">${esc(c.title[lang])}</h2>`}<div class="body">${paragraph(c.body[lang])}</div>${c.chart ? `<figure class="chart" data-chart="${c.chart}" data-chapter="${i}"></figure>` : ''}${c.diagram ? `<div class="diagram" data-diagram="${c.diagram}"></div>` : ''}${controls(c, i)}${c.microNote?.[lang] ? `<p class="micro">${esc(c.microNote[lang])}</p>` : ''}<button class="source-link" data-source="${i}">${tr('Sources & context ↗', '来源与背景 ↗')}</button>${i === 0 ? workCredit() : ''}${i === 13 ? `<div class="local-controls"><button id="explore-end">${tr('Explore the evidence ↗', '探索地图证据 ↗')}</button></div>${workCredit()}` : ''}</div></section>`).join('')}</main>
 <aside class="map-legend" aria-label="${tr('Map legend', '地图图例')}"></aside><div class="map-caption">BARCELONA · ${tr('NEIGHBOURHOOD EVIDENCE', '街区证据')}</div><div class="map-status" role="status" hidden></div>
 <aside class="explore-panel" hidden><h2>${tr('A closer look', '走近街区')}</h2><label for="theme-select">${tr('Map theme', '地图主题')}</label><select id="theme-select">${['M04', 'M05', 'M06', 'M07', 'M08', 'M03', 'M10'].map(m => `<option value="${m}">${themeTitle(m)}</option>`).join('')}</select><div class="explore-subcontrols"></div><label for="place-select">${tr('Neighbourhood', '街区')}</label><select id="place-select"><option value="">${tr('Choose a neighbourhood', '选择街区')}</option>${neighbourhoods.features.map(f => `<option value="${f.properties.id}">${esc(f.properties.name)}</option>`).join('')}</select><div class="explore-detail"></div><button class="back" id="explore-close">${tr('← Return to the story', '← 返回故事')}</button></aside>
 <dialog id="sheet"><button class="close" aria-label="${tr('Close', '关闭')}">×</button><div class="sheet-wrap"></div></dialog>`;
    if (existingMap && map) {
        document.getElementById('map')!.replaceWith(existingMap);
        existingMap.setAttribute('aria-label', tr('Barcelona evidence map', '巴塞罗那证据地图'));
        map.resize();
    }
    document.querySelectorAll<HTMLElement>('[data-goto]').forEach(b => b.onclick = () => go(Number(b.dataset.goto)));
    document.querySelectorAll<HTMLElement>('[data-dialog]').forEach(b => b.onclick = () => openDialog(b.dataset.dialog!));
    document.querySelectorAll<HTMLElement>('[data-source]').forEach(b => b.onclick = () => openDialog('sources', Number(b.dataset.source)));
    $('#sheet .close').onclick = () => $('#sheet' as string) instanceof HTMLDialogElement && ($('#sheet') as HTMLDialogElement).close();
    $('#language').onclick = () => { const save = active, wasExploring = exploring, saved = { ...exploreSaved }, theme = currentTheme(), place = selected; lang = lang === 'en' ? 'zh' : 'en'; localStorage.setItem('room-language', lang); render(); if (wasExploring) {
        exploring = false;
        openExplore();
        exploreSaved = saved;
        ($('#theme-select') as HTMLSelectElement).value = theme;
        renderExploreControls();
        applyTheme(theme, true);
        if (place)
            selectPlace(place);
    }
    else
        requestAnimationFrame(() => { go(save, false); applyTheme(currentTheme(), true); }); };
    $('#explore-open')?.addEventListener('click', openExplore);
    $('#explore-end')?.addEventListener('click', openExplore);
    $('#explore-close').onclick = closeExplore;
    $('#theme-select').onchange = () => { renderExploreControls(); applyTheme(($('#theme-select') as HTMLSelectElement).value, true); };
    $('#place-select').onchange = () => selectPlace(($('#place-select') as HTMLSelectElement).value);
    document.querySelectorAll<HTMLElement>('button[data-snapshot]').forEach(b => b.onclick = () => { snapshot = Number(b.dataset.snapshot); if (snapshot === 0)
        observationMode = 'count'; updateControls(); applyTheme(currentTheme()); renderCharts(); });
    document.querySelectorAll<HTMLElement>('button[data-platform-mode]').forEach(b => b.onclick = () => { if (currentTheme() === 'M10')
        observationMode = b.dataset.platformMode!;
    else
        platformMode = b.dataset.platformMode!; updateControls(); applyTheme(currentTheme()); });
    document.querySelectorAll<HTMLElement>('button[data-comparison]').forEach(b => b.onclick = () => { comparison = b.dataset.comparison!; updateControls(); applyTheme(currentTheme()); renderCharts(); });
    document.querySelectorAll<HTMLElement>('button[data-case]').forEach(b => b.onclick = () => { caseIndex = Number(b.dataset.case); updateControls(); applyTheme('M09', true); });
    renderCharts();
    renderDiagrams();
    updateControls();
    window.scrollTo({ top: y, behavior: 'instant' });
    if (exploring) activate(active); else updateScroll();
    if (simpleMap)
        fallback();
}
function controls(c: Chapter, i: number) {
    if (c.map === 'M10')
        return `<div class="local-controls" aria-label="${tr('Observation period', '观测时期')}">${['Sep 2025', 'Dec 2025', 'Mar 2026', 'Jun 2026'].map((v, j) => `<button data-snapshot="${j}" aria-pressed="${j === snapshot}">${lang === 'en' ? v : ['2025.09', '2025.12', '2026.03', '2026.06'][j]}</button>`).join('')}</div><div class="local-controls"><button data-platform-mode="count">${tr('All observed', '观测总量')}</button><button data-platform-mode="new">${tr('Newly observed', '相对上期新见')}</button><button data-platform-mode="lost">${tr('Not reobserved', '本期未再见')}</button></div>`;
    if (c.map === 'M03')
        return `<div class="local-controls"><button data-platform-mode="count">${tr('All listings', '全部房源')}</button><button data-platform-mode="entire">${tr('Entire homes', '整套房源')}</button><button data-platform-mode="short">${tr('Minimum ≤30 nights', '起订≤30晚')}</button><button data-platform-mode="share">${tr('Entire-home %', '格内整套占比')}</button></div>`;
    if (c.map === 'M08')
        return `<div class="local-controls"><button data-comparison="level">${tr('Rent level', '租金水平')}</button><button data-comparison="change">${tr('Rent change', '租金变化')}</button></div>`;
    if (c.map === 'M09' && i === 9)
        return `<div class="local-controls"><button data-case="0">${esc(caseList()[0]?.name || 'A')}</button><button data-case="1">${esc(caseList()[1]?.name || 'B')}</button></div>`;
    return '';
}
function updateControls() { for (const key of ['snapshot', 'platformMode', 'comparison', 'case'] as const)
    document.querySelectorAll<HTMLElement>(`button[data-${key.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}]`).forEach(el => { const val = { snapshot: String(snapshot), platformMode, comparison, case: String(caseIndex) }[key]; const chapter = el.closest<HTMLElement>('[data-index]'); const mode = key === 'platformMode' && chapter && content.chapters[Number(chapter.dataset.index)].map === 'M10' ? observationMode : val; const on = el.dataset[key] === mode; el.classList.toggle('active', on); el.setAttribute('aria-pressed', String(on)); if (el instanceof HTMLButtonElement && chapter && content.chapters[Number(chapter.dataset.index)].map === 'M10' && key === 'platformMode')
        el.disabled = snapshot === 0 && ['new', 'lost'].includes(el.dataset.platformMode || ''); }); }
function caseList(): any[] { const c = summary.cases; return Array.isArray(c) ? c : c?.selected ?? c?.cases ?? []; }
function currentTheme() { return exploring ? ($('#theme-select') as HTMLSelectElement).value : content.chapters[active].map; }
function go(i: number, smooth = true) { if (exploring)
    closeExplore(); jumpTarget = i; clearTimeout(jumpTimer); jumpTimer = window.setTimeout(() => { jumpTarget = null; updateScroll(); }, 1800); $('#chapter-' + content.chapters[i].id + ' .copy').scrollIntoView({ behavior: smooth && !reduced() ? 'smooth' : 'instant', block: 'start' }); history.replaceState(null, '', '#chapter-' + content.chapters[i].id); activate(i); }
function updateScroll() { if (!document.getElementById('story') || exploring || jumpTarget !== null)
    return; let next = 0; document.querySelectorAll<HTMLElement>('.chapter').forEach((el, i) => { if (el.getBoundingClientRect().top < innerHeight * .53)
    next = i; }); activate(next); const denom = document.documentElement.scrollHeight - innerHeight; $('.progress').style.width = `${denom > 0 ? Math.min(100, scrollY / denom * 100) : 0}%`; }
function activate(i: number) { const changed = i !== active; active = i; document.querySelectorAll('.chapter').forEach((e, j) => e.classList.toggle('active', i === j)); document.querySelectorAll('[data-goto]').forEach((e, j) => { e.classList.toggle('active', i === j); e.setAttribute('aria-current', i === j ? 'step' : 'false'); }); $('.hero-location').hidden = i !== 0; document.body.dataset.chapter = content.chapters[i].id; document.body.dataset.side = [1, 5, 6, 9, 11].includes(i) ? 'right' : 'left'; placeLegend(); if (changed) {
    applyTheme(content.chapters[i].map, true);
} }
window.addEventListener('scroll', () => { if (!scrollFrame)
    scrollFrame = requestAnimationFrame(() => { scrollFrame = 0; updateScroll(); }); }, { passive: true });
window.addEventListener('resize', () => { if (!document.getElementById('story')) return;
    map?.resize(); applyTheme(currentTheme(), true); }, { passive: true });
window.addEventListener('scrollend', () => { if (jumpTarget !== null) {
    jumpTarget = null;
    clearTimeout(jumpTimer);
    updateScroll();
} });
window.addEventListener('hashchange', () => { if (!document.getElementById('story')) return;
    const i = content.chapters.findIndex(c => '#chapter-' + c.id === location.hash); if (i >= 0)
    go(i, false); });
function initMap() {
    simpleMap = false;
    $('#map').hidden = false;
    $('#map-fallback').hidden = true;
    $('.map-status').hidden = true;
    document.body.dataset.mapReady = 'false';
    try {
        if (!baseStyle)
            throw new Error('Map style unavailable');
        if (!mapboxgl.supported())
            throw new Error('WebGL unavailable');
        mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;
        const storyStyle = structuredClone(baseStyle);
        // Studio stores the evidence design; chapter-specific layers control its display in the story.
        storyStyle.layers = storyStyle.layers.filter((layer: any) => !layer.id.startsWith('rtl-'));
        for (const [key, entry] of Object.entries(mapRegistry) as [string, any][]) {
            const existing = Object.entries(storyStyle.sources).find(([, source]: [string, any]) => source.url === 'mapbox://' + entry.tilesetId);
            if (existing && existing[0] !== key) {
                storyStyle.sources[key] = existing[1];
                delete storyStyle.sources[existing[0]];
            }
        }
        document.body.dataset.mapStyle = publishedStyleUrl || 'saved-base-style';
        map = new mapboxgl.Map({ container: 'map', style: storyStyle, center: [2.12, 41.39], zoom: 11.6, pitch: 0, bearing: 0, attributionControl: false, scrollZoom: false, dragPan: false, dragRotate: false, touchZoomRotate: false, doubleClickZoom: false, keyboard: false, fadeDuration: reduced() ? 0 : 180 });
        map.addControl(new mapboxgl.AttributionControl({ compact: true }));
        const attempt = map;
        const attemptStart = performance.now();
        let success = false;
        const resizeAttempt = () => {
            if (map !== attempt) return;
            attempt.resize();
            if (success) applyTheme(currentTheme(), true);
        };
        const observer = new ResizeObserver(resizeAttempt);
        observer.observe($('#map'));
        const resumeAttempt = () => {
            if (!document.hidden) {
                resizeAttempt();
                if (!exploring) updateScroll();
            }
        };
        document.addEventListener('visibilitychange', resumeAttempt);
        let loadTimer = 0;
        attempt.on('remove', () => {
            observer.disconnect();
            document.removeEventListener('visibilitychange', resumeAttempt);
            clearTimeout(loadTimer);
        });
        map.on('load', () => {
            ready = true; addEvidence(); success = true;
            document.body.dataset.mapReady = 'true';
            document.body.dataset.mapAttemptMs = String(Math.round(performance.now() - attemptStart));
            if (!document.body.dataset.firstMapMs) document.body.dataset.firstMapMs = String(Math.round(performance.now()));
            document.body.dataset.mapSource = mapRegistry.neighbourhoods?.tilesetId ? 'vector-tiles' : 'local-geojson';
            if (exploring) { map!.dragPan.enable(); map!.scrollZoom.enable(); map!.touchZoomRotate.enable(); map!.keyboard.enable(); }
            applyTheme(currentTheme(), true);
            if (exploring && selected) selectPlace(selected);
            $('.map-status').hidden = true; $('#map-fallback').hidden = true;
            const idx = content.chapters.findIndex(c => '#chapter-' + c.id === location.hash);
            if (!exploring && idx >= 0) go(idx, false);
            map!.once('idle', () => { if (!document.body.dataset.firstEvidenceIdleMs) document.body.dataset.firstEvidenceIdleMs = String(Math.round(performance.now())); });
        });
        map.on('movestart', () => { document.body.dataset.mapMoving = 'true'; });
        map.on('moveend', () => { document.body.dataset.mapMoving = 'false'; if (ready)
            renderLegend(currentTheme()); });
        map.on('error', e => { console.warn('Map resource unavailable', e.error?.message); if (!success) {
            $('.map-status').hidden = false;
            $('.map-status').textContent = tr('Some map resources are unavailable.', '部分地图资源暂不可用。');
        } });
        const checkLoading = () => {
            if (success || map !== attempt) return;
            if (document.hidden) {
                loadTimer = window.setTimeout(checkLoading, 15000);
            } else {
                showSimpleMap();
            }
        };
        loadTimer = window.setTimeout(checkLoading, 15000);
    }
    catch (e) {
        console.warn('Interactive map unavailable', e instanceof Error ? e.message : String(e));
        showSimpleMap();
    }
}
function showSimpleMap() {
    map?.remove();
    map = undefined;
    ready = false;
    document.body.dataset.mapReady = 'false';
    document.body.dataset.mapSource = 'simplified-svg';
    fallback();
}
function simpleMapStatus() {
    $('.map-status').hidden = false;
    $('.map-status').innerHTML = `${tr('Simplified map · full story and data', '简洁地图 · 保留完整故事与数据')} <button id="retry-map">${tr('Try interactive map', '重试交互地图')}</button>`;
    $('#retry-map').onclick = async () => {
        const button = $('#retry-map') as HTMLButtonElement;
        button.disabled = true;
        button.textContent = tr('Loading…', '正在载入…');
        try {
            if (!baseStyle) baseStyle = await loadMapStyle();
            if (!baseStyle) throw new Error('Map style unavailable');
            initMap();
        } catch {
            simpleMapStatus();
        }
    };
}
function sourceDef(key: string, data: Collection): any { const r = mapRegistry[key]; return r?.tilesetId ? { type: 'vector', url: 'mapbox://' + r.tilesetId } : { type: 'geojson', data, promoteId: 'id' }; }
function srcLayer(key: string): any { return mapRegistry[key]?.sourceLayer ? { 'source-layer': mapRegistry[key].sourceLayer } : {}; }
function addEvidence() {
    if (!map)
        return;
    if (!map.getSource('neighbourhoods')) map.addSource('neighbourhoods', sourceDef('neighbourhoods', neighbourhoods));
    if (!map.getSource('hut')) map.addSource('hut', sourceDef('hut', hut));
    if (!map.getSource('grid')) map.addSource('grid', sourceDef('grid', grid));
    if (!map.getSource('places')) map.addSource('places', sourceDef('places', places));
    map.addSource('city-context', {type:'geojson', data:cityContext});
    map.addLayer({ id: 'evidence-fill', type: 'fill', source: 'neighbourhoods', ...srcLayer('neighbourhoods'), paint: { 'fill-color': '#343434', 'fill-opacity': .74, 'fill-outline-color': '#888' } });
    map.addLayer({ id: 'evidence-boundary', type: 'line', source: 'neighbourhoods', ...srcLayer('neighbourhoods'), paint: { 'line-color': '#b7b7b7', 'line-width': .6, 'line-opacity': .48 } });
    map.addLayer({id:'district-boundary', type:'line', source:'city-context', filter:['==',['get','kind'],'district'], paint:{'line-color':'#d28b61','line-width':1.2,'line-opacity':.8}});
    map.addLayer({id:'city-boundary', type:'line', source:'city-context', filter:['==',['get','kind'],'city'], paint:{'line-color':'#eea275','line-width':2.2,'line-opacity':1}});
    map.addLayer({ id: 'evidence-highlight', type: 'line', source: 'neighbourhoods', ...srcLayer('neighbourhoods'), filter: ['==', ['get', 'id'], '22'], paint: { 'line-color': '#f0b396', 'line-width': 2, 'line-opacity': 1 } });
    map.addLayer({ id: 'hut-points', type: 'circle', source: 'hut', ...srcLayer('hut'), layout: { visibility: 'none' }, paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1.2, 13, 2.2, 16, 4], 'circle-color': '#efb894', 'circle-opacity': .75 } });
    map.addSource('hut-clusters', { type: 'geojson', data: hut, cluster: true, clusterRadius: 35, clusterMaxZoom: 12 });
    map.addLayer({ id: 'hut-cluster-circles', type: 'circle', source: 'hut-clusters', filter: ['has', 'point_count'], layout: { visibility: 'none' }, paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'], 1, 5, 500, 19, 2000, 32], 'circle-color': '#c9a58d', 'circle-opacity': .72, 'circle-stroke-color': '#e7d8ce', 'circle-stroke-width': .5 } });
    map.addLayer({ id: 'hut-cluster-single', type: 'circle', source: 'hut-clusters', filter: ['!', ['has', 'point_count']], maxzoom: 12, layout: { visibility: 'none' }, paint: { 'circle-radius': 2, 'circle-color': '#c9a58d', 'circle-opacity': .8 } });
    map.addLayer({ id: 'hut-cluster-labels', type: 'symbol', source: 'hut-clusters', filter: ['has', 'point_count'], layout: { visibility: 'none', 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Regular'], 'text-size': 11 }, paint: { 'text-color': '#121212' } });
    map.addLayer({ id: 'grid-fill', type: 'fill', source: 'grid', ...srcLayer('grid'), layout: { visibility: 'none' }, paint: { 'fill-color': '#c7764d', 'fill-opacity': .8, 'fill-outline-color': '#525252' } });
    const centers: Collection = { type: 'FeatureCollection', features: grid.features.map(f => ({ ...f, geometry: { type: 'Point', coordinates: centroid(f.geometry) } })) };
    map.addSource('grid-centres', { type: 'geojson', data: centers });
    map.addLayer({ id: 'grid-circles', type: 'circle', source: 'grid-centres', layout: { visibility: 'none' }, paint: { 'circle-radius': 3, 'circle-color': '#e7a781', 'circle-opacity': .75, 'circle-stroke-color': '#efcdb4', 'circle-stroke-width': .4 } });
    map.addLayer({ id: 'place-outline', type: 'line', source: 'places', ...srcLayer('places'), layout: { visibility: 'none' }, paint: { 'line-color': '#e5624d', 'line-width': 2, 'line-dasharray': [3, 2] } });
    map.on('click', 'evidence-fill', e => { if (exploring && e.features?.[0])
        selectPlace(String(e.features[0].properties?.id), false); });
}
function centroid(g: any): number[] { const pts: number[][] = []; function walk(a: any) { if (typeof a[0] === 'number') {
    pts.push(a);
}
else
    for (const q of a)
        walk(q); } if (g.type === 'GeometryCollection')
    g.geometries.forEach((q: any) => walk(q.coordinates));
else
    walk(g.coordinates); return [pts.reduce((a, b) => a + b[0], 0) / pts.length, pts.reduce((a, b) => a + b[1], 0) / pts.length]; }
function bounds(g: any): [
    [
        number,
        number
    ],
    [
        number,
        number
    ]
] { const pts: number[][] = []; function walk(a: any) { if (typeof a[0] === 'number')
    pts.push(a);
else
    for (const q of a)
        walk(q); } if (g.type === 'GeometryCollection')
    g.geometries.forEach((q: any) => walk(q.coordinates));
else
    walk(g.coordinates); return [[Math.min(...pts.map(p => p[0])), Math.min(...pts.map(p => p[1]))], [Math.max(...pts.map(p => p[0])), Math.max(...pts.map(p => p[1]))]]; }
const numerical = (f: string): any => ['coalesce', ['get', f], 0];
function extent(field: string) { const valid = field === 'rent2025' ? 'validRent2025' : field === 'rentChange' ? 'validRentChange' : field === 'contractIntensity' ? 'validContractActivity' : 'comparable'; const a = neighbourhoods.features.filter(f => f.properties[valid] !== false && f.properties.comparable !== false).map(f => f.properties[field]).filter(v => typeof v === 'number' && Number.isFinite(v)); return a.length ? [Math.min(...a), Math.max(...a)] : [0, 1]; }
function fillFor(m: string): any {
    if (m === 'M08')
        return ['match', ['get', comparison === 'change' ? 'changeClass' : 'overlapClass'], ...Object.entries(categories).flat(), '#222222'];
    const f = themeField[m];
    if (!f)
        return '#2f2f2f';
    const [lo, hi] = extent(f);
    let expression: any;
    if (m === 'M06') {
        const lim = Math.max(Math.abs(lo), Math.abs(hi), 1);
        expression = ['interpolate', ['linear'], ['get', f], -lim, '#444444', 0, '#d8d8d8', lim, '#bb4436'];
    }
    else
        expression = ['interpolate', ['linear'], ['get', f], lo, m === 'M07' ? '#333333' : '#79746f', Math.max(lo + .001, hi), m === 'M05' ? '#bf483e' : m === 'M07' ? '#ddd' : '#dc955e'];
    const valid = m === 'M05' ? 'validRent2025' : m === 'M06' ? 'validRentChange' : m === 'M07' ? 'validContractActivity' : 'comparable';
    return ['case', ['any', ['==', ['get', f], null], ['==', ['get', valid], false], ['==', ['get', 'comparable'], false]], '#222222', expression];
}
function applyTheme(m: string, move = false) {
    placeLegend();
    document.body.dataset.mapTheme = m;
    document.body.dataset.mapMode = m === 'M10' ? observationMode : m === 'M03' ? platformMode : m === 'M08' ? comparison : 'level';
    document.body.dataset.snapshot = String(snapshot);
    document.body.dataset.case = String(caseList()[caseIndex]?.id ?? '');
    renderLegend(m);
    if (!ready || !map) {
        if (!$('#map-fallback').hidden)
            fallback();
        return;
    }
    const visible = (id: string, v: boolean) => map!.setLayoutProperty(id, 'visibility', v ? 'visible' : 'none');
    for (const id of ['hut-points', 'hut-cluster-circles', 'hut-cluster-labels', 'hut-cluster-single', 'grid-fill', 'grid-circles', 'place-outline'])
        visible(id, false);
    map.setPaintProperty('evidence-fill', 'fill-color', fillFor(m));
    map.setPaintProperty('evidence-fill', 'fill-opacity', ['M01', 'M02', 'M03', 'M10', 'M09'].includes(m) ? .30 : .87);
    const cityView = m === 'M01';
    visible('district-boundary', cityView);
    visible('city-boundary', cityView);
    map.setPaintProperty('evidence-boundary', 'line-color', cityView ? '#b47857' : '#b7b7b7');
    map.setPaintProperty('evidence-boundary', 'line-width', cityView ? .65 : .6);
    map.setPaintProperty('evidence-boundary', 'line-opacity', cityView ? .5 : m === 'M03' || m === 'M10' ? .18 : .5);
    const cases = caseList();
    const caseId = active === 11 && !exploring ? '07' : String(cases[caseIndex]?.id ?? cases[caseIndex]?.barriId ?? '22').padStart(2, '0');
    let highlight = exploring && selected ? selected : m === 'M09' ? caseId : '';
    document.body.dataset.mapFocus = cityView ? 'barcelona-city-10-districts-73-neighbourhoods' : highlight;
    map.setFilter('evidence-highlight', ['==', ['get', 'id'], highlight]);
    if (m === 'M02') {
        visible('hut-cluster-single', true);
        visible('hut-points', true);
        visible('hut-cluster-circles', true);
        visible('hut-cluster-labels', true);
        map.setLayerZoomRange('hut-points', 12, 24);
    }
    if (m === 'M03' || m === 'M10') {
        const t = m === 'M03' ? 3 : snapshot;
        if (platformMode === 'share' && m === 'M03') {
            visible('grid-fill', true);
            map.setPaintProperty('grid-fill', 'fill-color', ['case', ['==', ['get', 'share' + t], null], '#222222', ['interpolate', ['linear'], ['get', 'share' + t], 0, '#777777', 100, '#d77943']]);
        }
        else {
            visible('grid-circles', true);
            const key = m === 'M10' && ['new', 'lost'].includes(observationMode) ? (t > 0 ? observationMode + t : 'none') : m === 'M03' && ['entire', 'short'].includes(platformMode) ? platformMode + t : 'n' + t;
            const max = Math.max(...grid.features.flatMap(f => [0, 1, 2, 3].map(j => Number(f.properties['n' + j]) || 0)), 1);
            map.setFilter('grid-circles', ['>', numerical(key), 0]);
            map.setPaintProperty('grid-circles', 'circle-radius', ['interpolate', ['linear'], ['zoom'], 10, ['*', 1.2, ['sqrt', ['/', numerical(key), max]]], 12, ['*', 22, ['sqrt', ['/', numerical(key), max]]], 15, ['*', 48, ['sqrt', ['/', numerical(key), max]]]]);
            map.setPaintProperty('grid-circles', 'circle-color', m === 'M10' && observationMode === 'lost' ? '#cb6254' : '#e4ad83');
        }
    }
    if (m === 'M09') {
        visible('place-outline', true);
        map.setFilter('place-outline', ['==', ['get', 'barri_id'], caseId]);
        map.setPaintProperty('evidence-fill', 'fill-color', ['match', ['get', 'overlapClass'], ...Object.entries(categories).flat(), '#222222']);
    }
    if (move) {
        map.stop();
        let box: [
            [
                number,
                number
            ],
            [
                number,
                number
            ]
        ] = [[2.084, 41.347], [2.227, 41.455]];
        if (m === 'M01') box = bounds(cityContext.features.find(f => f.properties.kind === 'city')!.geometry);
        if (m === 'M09') {
            const f = neighbourhoods.features.find(f => f.properties.id === caseId);
            if (f)
                box = bounds(f.geometry);
        }
        const right = !mobile() && $('.chapter.active')?.classList.contains('right');
        const pad = mobile() ? { top: 220, bottom: 160, left: 25, right: 30 } : { top: 100, bottom: 85, left: right ? 80 : 430, right: right ? 440 : 80 };
        map.fitBounds(box, { padding: pad, maxZoom: m === 'M09' ? 13.7 : 12.2, duration: reduced() ? 0 : m === 'M09' ? 850 : 500 });
    }
}
function themeTitle(m: string) { return ({ M01: tr('Barcelona · a city to live in', '巴塞罗那 · 可以住下来的城市'), M02: tr('Tourist-home registrations', '旅游住房登记'), M03: tr('Airbnb listings', 'Airbnb 房源'), M04: tr('Tourist homes / 1,000 dwellings', '旅游住房登记 / 千套住宅'), M05: tr('New-lease rent', '新登记租约租金'), M06: tr('Rent change before inflation adjustment', '租金变化（未扣除通胀）'), M07: tr('New contracts / 1,000 dwellings', '新合同 / 千套住宅'), M08: tr('Overlap and mismatch', '重合与错位'), M09: tr('Back to the neighbourhood', '回到街区'), M10: tr('Airbnb across four dates', '四期 Airbnb 房源') } as Record<string, string>)[m] || m; }
function placeLegend() { const legend = $('.map-legend'); if (!legend)
    return; legend.classList.toggle('on-left', !mobile() && !exploring && [1, 5, 6, 9, 11].includes(active)); const parent = mobile() && !exploring ? $('.chapter.active') : $('#app'); if (parent && legend.parentElement !== parent)
    parent.appendChild(legend); }
function renderLegend(m: string) {
    const el = $('.map-legend');
    if (!el)
        return;
    el.hidden = false;
    let body = '', note = '';
    if (m === 'M01') {
        body = `<div class="legend-category"><i class="line-key city"></i>${tr('Barcelona municipal boundary', '巴塞罗那市界')}</div><div class="legend-category"><i class="line-key district"></i>${tr('10 administrative districts', '10 个行政区的区界')}</div><div class="legend-category"><i class="line-key neighbourhood"></i>${tr('73 neighbourhoods', '73 个街区的边界')}</div>`;
        note = tr('The neighbourhood is the unit used throughout this story.', '后文以街区为单位比较住房与租金。');
    }
    else if (m === 'M08' || m === 'M09') {
        const change = m === 'M08' && comparison === 'change';
        const labels = { both: tr('Both high', '两项都高'), tourism: tr('Tourist homes high only', '仅旅游住房较多'), rent: change ? tr('Rent growth high only', '仅租金涨幅较高') : tr('Rent high only', '仅租金较高'), neither: tr('Neither high', '两项都不高'), unavailable: tr('Not comparable', '无法比较') };
        body = Object.entries(categories).map(([k, v]) => `<div class="legend-category"><i style="background:${v}"></i>${labels[k as keyof typeof labels]}</div>`).join('');
        note = tr(`Tourist homes 2026 · Rent ${change ? 'growth 2022–2025' : 'level 2025'}. High = top quarter`, `旅游住房2026 · ${change ? '租金涨幅2022—2025' : '租金2025'}。高＝排名前四分之一`);
    }
    else if (themeField[m]) {
        const f = themeField[m], [lo, hi] = extent(f);
        const colors = m === 'M06' ? '#444,#d8d8d8,#bb4436' : m === 'M05' ? '#79746f,#bf483e' : m === 'M07' ? '#333,#ddd' : '#79746f,#dc955e';
        const a = m === 'M06' ? -Math.max(Math.abs(lo), Math.abs(hi)) : lo, b = m === 'M06' ? -a : hi;
        body = `<div class="legend-scale" style="background:linear-gradient(90deg,${colors})"></div><div class="legend-values"><span>${fmt(a)}</span><span>${fmt(b)}</span></div>`;
        note = m === 'M05' ? tr('€/m²/month · 2025 registered contracts', '欧元/平方米/月 · 2025新登记合同') : m === 'M06' ? tr('% · 2022 → 2025 · nominal prices', '% · 2022 → 2025 · 名义价格') : m === 'M07' ? tr('2025 contracts / 2025 cadastral dwellings', '2025合同 / 2025地籍住宅') : tr('2026 registrations / 2026 cadastral dwellings', '2026登记 / 2026地籍住宅');
    }
    else if (m === 'M02') {
        body = `<div class="legend-category"><i style="background:#c9a58d;border-radius:50%"></i>${tr('Numbers count grouped registrations', '圆内数字表示合并显示的登记条数')}</div>`;
        note = tr('Public register · May 2026 update', '公开登记 · 2026年5月更新');
    }
    else {
        const t = m === 'M03' ? 3 : snapshot;
        const d = summary.platformDates[t];
        body = `<div class="legend-category"><i style="background:#e4ad83;border-radius:50%"></i>${m === 'M03' && platformMode === 'share' ? tr('Entire-home share · 0–100%', '整套份额 · 0—100%') : tr('Circle area represents records', '圆面积表示记录数量')}</div>`;
        note = `${d?.actualStart ?? ''} — ${d?.actualEnd ?? ''} · 500 m`;
        if (m === 'M10' && snapshot === 0)
            note += ' · ' + tr('First observation; no previous period', '首次观测，无前期比较');
        if (m === 'M03' && platformMode === 'share')
            body = `<div class="legend-scale" style="background:linear-gradient(90deg,#777777,#d77943)"></div><div class="legend-values"><span>0%</span><span>50%</span><span>100%</span></div><p class="legend-explain">${tr('Entire-home listings ÷ listings with a known room type in the same 500 m cell. At 50%, half of those listings are entire homes.', '该格内整套房源 ÷ 该格内房型已知的房源。50% 表示这些房源中一半是整套住房。')}</p><div class="legend-category"><i style="background:#222;border:1px solid #777"></i>${tr('No listings observed in this period', '本期未观测到房源')}</div>`;
        else
            body += circleKey();
        if (m === 'M10' && observationMode !== 'count')
            note += ' · ' + tr('fixed reference position', '固定参考位置');
    }
    if (m === 'M08' || m === 'M09') {
        const o = summary.overlap[m === 'M08' && comparison === 'change' ? 'change' : 'level'];
        note += ' · ' + tr(`${o.intersection} of ${o.sampleN} are high on both measures`, `${o.sampleN} 个街区中，${o.intersection} 个两项都高`);
        note += ' · HUT ≥ ' + fmt(o.hutThreshold, 1) + ' / 1,000; ' + (m === 'M08' && comparison === 'change' ? tr('rent growth ≥ ', '租金涨幅 ≥ ') : tr('rent ≥ ', '租金 ≥ ')) + fmt(o.rentThreshold, 1) + (m === 'M08' && comparison === 'change' ? '%' : ' €/m²/month');
    }
    const mode = m === 'M03' ? ({ count: tr('All listings', '全部房源'), entire: tr('Entire homes', '整套房源'), short: tr('Minimum booking ≤30 nights', '最低预订晚数≤30晚'), share: tr('Entire-home %', '格内整套占比') } as Record<string, string>)[platformMode] : m === 'M10' ? ({ count: tr('All observed', '观测总量'), new: tr('Newly observed since previous period', '相对上期新见'), lost: tr('Not reobserved from previous period', '本期未再见') } as Record<string, string>)[observationMode] : '';
    if (themeField[m] && m !== 'M08')
        body += `<div class="legend-category"><i style="background:#222;border:1px solid #777"></i>${tr('Not comparable / insufficient records', '不可比 / 有效记录不足')}</div>`;
    el.innerHTML = `<h3>${themeTitle(m)}</h3>${mode ? `<p>${mode}</p>` : ''}${body}<p>${esc(note)}</p>`;
    placeLegend();
}
function circleKey() { const max = Math.max(...grid.features.flatMap(f => [0, 1, 2, 3].map(j => Number(f.properties['n' + j]) || 0)), 1); const z = map?.getZoom() ?? 12; const size = z < 12 ? 1.2 + (z - 10) * 10.4 : 22 + Math.min(3, z - 12) * 26 / 3; const values = [Math.round(max / 16), Math.round(max / 4), max]; return `<svg viewBox="0 0 260 ${Math.max(45, 2 * size + 25)}" aria-label="${tr('Circle size key', '圆面积图例')}">${values.map((v, i) => `<circle cx="${40 + i * 85}" cy="${size + 2}" r="${Math.max(.5, size * Math.sqrt(v / max))}" fill="none" stroke="#e4ad83"/><text x="${40 + i * 85}" y="${2 * size + 20}" text-anchor="middle" fill="#ccc" font-size="11">${fmt(v, 0)}</text>`).join('')}</svg>`; }
function openExplore() { if (exploring) return; exploreSaved = { index: active, y: scrollY, anchorTop: $('#chapter-' + content.chapters[active].id + ' .copy').getBoundingClientRect().top }; exploring = true; $('#story').hidden = true; $('.chapter-rail').hidden = true; $('.hero-location').hidden = true; $('.explore-panel').hidden = false; map?.dragPan.enable(); map?.scrollZoom.enable(); map?.touchZoomRotate.enable(); map?.keyboard.enable(); renderExploreControls(); applyTheme(($('#theme-select') as HTMLSelectElement).value, true); $('#theme-select').focus(); }
function renderExploreControls() {
    const m = ($('#theme-select') as HTMLSelectElement).value;
    const el = $('.explore-subcontrols');
    const options = (items: [
        string,
        string
    ][], current: string) => items.map(([value, label]) => `<option value="${value}" ${value === current ? 'selected' : ''}>${label}</option>`).join('');
    el.innerHTML = m === 'M03' ? `<label for="explore-mode">${tr('Accommodation measure', '住宿指标')}</label><select id="explore-mode">${options([['count', tr('All listings', '全部房源')], ['entire', tr('Entire homes', '整套房源')], ['short', tr('Minimum ≤30 nights', '起订≤30晚')], ['share', tr('Entire-home %', '格内整套占比')]], platformMode)}</select>` : m === 'M10' ? `<label for="explore-period">${tr('Observation window', '观测窗口')}</label><select id="explore-period">${options(summary.platformDates.map((r: any, i: number) => [String(i), r.actualStart + ' — ' + r.actualEnd]), String(snapshot))}</select><label for="explore-mode">${tr('Records', '记录')}</label><select id="explore-mode">${options(snapshot === 0 ? [['count', tr('All observed', '观测总量')]] : [['count', tr('All observed', '观测总量')], ['new', tr('Newly observed', '相对上期新见')], ['lost', tr('Not reobserved', '本期未再见')]], observationMode)}</select>` : m === 'M08' ? `<label for="explore-comparison">${tr('Rent comparison', '租金比较')}</label><select id="explore-comparison">${options([['level', tr('Rent level', '租金水平')], ['change', tr('Rent change', '租金变化')]], comparison)}</select>` : '';
    $('#explore-mode')?.addEventListener('change', () => { const value = ($('#explore-mode') as HTMLSelectElement).value; if (m === 'M03')
        platformMode = value;
    else
        observationMode = value; updateControls(); applyTheme(m); });
    $('#explore-period')?.addEventListener('change', () => { snapshot = Number(($('#explore-period') as HTMLSelectElement).value); if (snapshot === 0)
        observationMode = 'count'; renderExploreControls(); updateControls(); renderCharts(); applyTheme(m); });
    $('#explore-comparison')?.addEventListener('change', () => { comparison = ($('#explore-comparison') as HTMLSelectElement).value; updateControls(); renderCharts(); applyTheme(m); });
}
function closeExplore() { exploring = false; $('#story').hidden = false; $('.chapter-rail').hidden = false; $('.explore-panel').hidden = true; map?.dragPan.disable(); map?.scrollZoom.disable(); map?.touchZoomRotate.disable(); map?.keyboard.disable(); const anchor = $('#chapter-' + content.chapters[exploreSaved.index].id + ' .copy'); const restoredY = anchor.getBoundingClientRect().top + scrollY - exploreSaved.anchorTop; window.scrollTo({ top: restoredY, behavior: 'instant' }); active = exploreSaved.index; activate(active); applyTheme(currentTheme(), true); }
function selectPlace(id: string, fly = true) { selected = id; const f = neighbourhoods.features.find(f => f.properties.id === id); if (!f) {
    $('.explore-detail').innerHTML = '';
    applyTheme(currentTheme());
    return;
} const p = f.properties; const quality = p.comparable === false ? tr('Statistical scopes remain unresolved; excluded from comparisons.', '统计范围尚待核对，不参与比较。') : !p.validRent2025 || !p.validRentChange ? tr('Rent comparisons do not meet the contract-count threshold.', '租金比较未满足合同数量门槛。') : ''; ($('#place-select') as HTMLSelectElement).value = id; $('.explore-detail').innerHTML = `<h3>${esc(p.name)}</h3><p>${tr('Tourist homes / 1,000 dwellings', '旅游住房登记 / 千套住宅')} <strong>${fmt(p.hutIntensity)}</strong><br>${tr('Rent · €/m²/month', '租金 · 欧元/平方米/月')} <strong>${fmt(p.rent2025, 2)}</strong><br>${tr('Rent change · 2022–25', '租金变化 · 2022—25')} <strong>${fmt(p.rentChange)}%</strong><br>${tr('New contracts / 1,000 dwellings', '新合同 / 千套住宅')} <strong>${fmt(p.contractIntensity)}</strong></p>${quality ? `<p class="notice">${quality}</p>` : ''}`; document.body.dataset.mapFocus = id; if (simpleMap) fallback(); if (!ready || !map) return; map.setFilter('evidence-highlight', ['==', ['get', 'id'], id]); if (fly)
    map.fitBounds(bounds(f.geometry), { padding: mobile() ? { top: 390, bottom: 130, left: 35, right: 35 } : { top: 100, bottom: 100, left: 430, right: 100 }, duration: reduced() ? 0 : 650, maxZoom: 14 }); }
function openDialog(which: string, chapterIndex?: number) {
    const wrap = $('#sheet .sheet-wrap');
    let body = '';
    if (which === 'contents')
        body = `<p class="kicker">${tr('The story', '故事目录')}</p><h2>${tr('Who gets to stay?', '谁能留下？')}</h2><ol class="contents-list">${content.chapters.map((c, i) => `<li><button data-sheet-goto="${i}"><small>${c.id}</small>${esc(c.title[lang])}</button></li>`).join('')}</ol><p><button id="sheet-explore">${tr('Explore the map ↗', '探索地图 ↗')}</button> · <button data-switch-dialog="method">${tr('Method', '方法')}</button> · <button data-switch-dialog="sources">${tr('Sources', '来源')}</button></p>`;
    if (which === 'sources') {
        const ids = chapterIndex === undefined ? null : content.chapters[chapterIndex].sourceIds;
        const subset = ids ? sources.filter(s => ids.includes(s.source_id || s.id)) : sources;
        body = `<p class="kicker">${tr('Sources & context', '来源与背景')}</p><h2>${chapterIndex === undefined ? tr('Where the evidence comes from', '证据从何而来') : esc(content.chapters[chapterIndex].title[lang])}</h2>${subset.map(s => `<article class="source-item"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(typeof s.title === 'object' ? s.title[lang] : s.title)} ↗</a><p>${esc(s.publisher || s.institution || '')} ${esc(s.date || s.published_date || '')}</p><p>${esc(typeof s.summary === 'object' ? s.summary[lang] : typeof s.paraphrase === 'object' ? s.paraphrase[lang] : s.summary || s.paraphrase || s.scope || '')}</p>${s.links?.length ? `<div class="source-extra">${s.links.map((link:any) => `<a href="${esc(link.download ? import.meta.env.BASE_URL + link.url : link.url)}" ${link.download ? `download="${esc(link.download)}"` : 'target="_blank" rel="noopener noreferrer"'}>${esc(typeof link.label === 'object' ? link.label[lang] : link.label)} ${link.download ? '↓' : '↗'}</a>`).join('')}</div>` : ''}${s.accessNote ? `<p class="source-access">${esc(s.accessNote[lang] || s.accessNote)}</p>` : ''}</article>`).join('')}`;
    }
    if (which === 'method')
        body = `<p class="kicker">${tr('Research method', '研究方法')}</p><h2>${tr('From public records to a housing story', '这个住房故事是怎样做出来的')}</h2><p>${esc(content.objective[lang])}</p><ol class="method-steps">${(content.methodSteps || []).map((step:any,i:number) => `<li><span class="method-number">${String(i+1).padStart(2,'0')}</span><div><h3>${esc(step.title[lang])}</h3>${paragraph(step.body[lang])}</div></li>`).join('')}</ol>`;
    wrap.innerHTML = body;
    const dialog = $('#sheet') as HTMLDialogElement;
    wrap.querySelector('h2')!.id = 'sheet-title';
    dialog.setAttribute('aria-labelledby', 'sheet-title');
    if (!dialog.open)
        dialog.showModal();
    dialog.scrollTop = 0;
    document.querySelectorAll<HTMLElement>('[data-sheet-goto]').forEach(b => b.onclick = () => { dialog.close(); go(Number(b.dataset.sheetGoto)); });
    $('#sheet-explore')?.addEventListener('click', () => { dialog.close(); openExplore(); });
    document.querySelectorAll<HTMLElement>('[data-switch-dialog]').forEach(b => b.onclick = () => openDialog(b.dataset.switchDialog!));

}
function renderCharts() { document.querySelectorAll<HTMLElement>('[data-chart]').forEach(el => { const id = el.dataset.chart!; el.innerHTML = chartSVG(id, Number(el.dataset.chapter)); }); }
function chartSVG(id: string, ch: number): string {
    const charts = summary.charts || {};
    const width = 350, height = 155, pad = 28;
    let caption = '', svg = '';
    if (id === 'C01' || id === 'C03') {
        const counts = id === 'C03', paired = id === 'C01' && ch === 6;
        const series: {name:string;color:string;rows:{year:number;value:number}[]}[] = paired
            ? ['23','40'].map((place,i)=>({name:neighbourhoods.features.find(f=>f.properties.id===place)!.properties.name,color:i===0?'#e5624d':'#dfb08d',rows:(charts.neighbourhoodRent || []).filter((r:any)=>r.id===place).map((r:any)=>({year:r.year,value:r.rentM2}))}))
            : [{name:tr('Barcelona','巴塞罗那'),color:'#e5624d',rows:(charts.cityRent || []).map((r:any)=>({year:r.year,value:counts?r.contracts:r.rentM2}))}];
        const w=420,h=190,left=counts?52:35,right=410,top=28,bottom=160;
        const ymin=counts?20000:paired?10:12,ymax=counts?60000:paired?24:18;
        const x=(year:number)=>left+(year-2019)/6*(right-left),y=(v:number)=>bottom-(v-ymin)/(ymax-ymin)*(bottom-top);
        const ticks=counts?[20000,40000,60000]:paired?[10,15,20]:[12,14,16,18];
        caption = counts ? tr('New residential contracts · Barcelona', '巴塞罗那新登记住宅租赁合同数') : paired ? tr('Two neighbourhoods · € / m² / month', '两个街区的租金 · 欧元/平方米/月') : tr('Barcelona rent · € / m² / month', '巴塞罗那租金 · 欧元/平方米/月');
        svg = `${ticks.map(v=>`<line class="gridline" x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end">${counts?fmt(v/1000,0)+'k':v}</text>`).join('')}<line class="axis" x1="${left}" x2="${right}" y1="${bottom}" y2="${bottom}"/>${[2019,2021,2023,2025].map(year=>`<text x="${x(year)}" y="182" text-anchor="${year===2019?'start':year===2025?'end':'middle'}">${year}</text>`).join('')}${paired?`<line class="threshold" x1="${x(2022)}" x2="${x(2022)}" y1="${top}" y2="${bottom}"/><text x="${x(2022)}" y="17" text-anchor="middle">${tr('2022 base year','2022 比较起点')}</text>`:''}${series.map(line=>`<path fill="none" stroke="${line.color}" stroke-width="2" d="${line.rows.map((r,i)=>(i?'L':'M')+x(r.year)+','+y(r.value)).join(' ')}"/>${line.rows.map(r=>`<circle cx="${x(r.year)}" cy="${y(r.value)}" r="2.6" fill="${line.color}"><title>${esc(line.name)} ${r.year}: ${fmt(r.value,counts?0:2)}</title></circle>${r.year===2025?`<text x="${x(r.year)}" y="${y(r.value)-9}" text-anchor="end">${fmt(r.value,counts?0:2)}</text>`:''}`).join('')}`).join('')}`;
        return `<figcaption>${caption}</figcaption><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(caption)}">${svg}</svg>${paired?`<div class="chart-key">${series.map(line=>`<span><i style="background:${line.color}"></i>${esc(line.name)}</span>`).join('')}</div>`:''}${counts?`<p class="chart-reading">${tr('k = 1,000 contracts. Each point is a calendar-year total.', 'k 表示千份合同；每个点为一整年的合同总数。')}</p>`:''}`;
    }
    else if (id === 'C02') {
        const totals: Record<string, number> = {};
        (summary.composition || charts.platformComposition || []).filter((r:any) => r.snapshotIndex === 3).forEach((r:any) => {totals[r.roomType] = (totals[r.roomType] || 0) + Number(r.records);});
        const entries = ['Entire home/apt','Private room','Shared room','Hotel room'].map(name => [name, totals[name] || 0] as const);
        const total = entries.reduce((n,row) => n+row[1],0);
        const labels:Record<string,string> = {'Entire home/apt':tr('Entire home / apartment','整套住房'),'Private room':tr('Private room','独立房间'),'Shared room':tr('Shared room','共享房间'),'Hotel room':tr('Hotel room','酒店房间')};
        return `<figcaption>${tr('Airbnb room types · June–July 2026', 'Airbnb 房型 · 2026年6—7月')}</figcaption><div class="composition-list">${entries.map(([name,n],i) => `<div class="composition-row"><span>${labels[name]}</span><span class="composition-value">${fmt(n,0)} <b>${fmt(n/total*100,1)}%</b></span><div class="composition-track"><i style="width:${n/total*100}%;background:${i===0?'#df9c71':'#aaa'}"></i></div></div>`).join('')}</div>`;
    }
    else if (id === 'C04') {
        const change = comparison === 'change', field = change ? 'rentChange' : 'rent2025', classField = change ? 'changeClass' : 'overlapClass';
        const o = summary.overlap[comparison];
        const fs = neighbourhoods.features.filter(f => f.properties[classField] !== 'unavailable' && Number.isFinite(f.properties[field]));
        const w=420,h=255,left=45,right=410,top=35,bottom=205;
        const xmin=0,xmax=70,ymin=change?-5:8,ymax=change?40:25;
        const x=(v:number)=>left+(v-xmin)/(xmax-xmin)*(right-left),y=(v:number)=>bottom-(v-ymin)/(ymax-ymin)*(bottom-top);
        const yTicks=change?[0,10,20,30,40]:[10,15,20,25];
        const yTitle=change?tr('Rent change, 2022–2025 (%)','2022—2025 租金涨幅（%）'):tr('2025 rent (€ / m² / month)','2025 租金（欧元/平方米/月）');
        caption = change ? tr('Do rents rise fastest where tourist homes concentrate?', '旅游住房多的地方，租金涨得更快吗？') : tr('Do tourist homes concentrate in expensive neighbourhoods?', '旅游住房多的地方，租金更贵吗？');
        svg = `<text class="chart-axis-title" x="${left}" y="15">${yTitle}</text>${yTicks.map(v=>`<line class="gridline" x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end">${v}</text>`).join('')}${[0,20,40,60].map(v=>`<line class="gridline" x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${bottom}"/><text x="${x(v)}" y="${bottom+18}" text-anchor="middle">${v}</text>`).join('')}<line class="axis" x1="${left}" x2="${right}" y1="${bottom}" y2="${bottom}"/><line class="axis" x1="${left}" x2="${left}" y1="${top}" y2="${bottom}"/><line class="threshold" x1="${x(o.hutThreshold)}" x2="${x(o.hutThreshold)}" y1="${top}" y2="${bottom}"/><line class="threshold" x1="${left}" x2="${right}" y1="${y(o.rentThreshold)}" y2="${y(o.rentThreshold)}"/>${fs.map(f=>`<circle cx="${x(f.properties.hutIntensity)}" cy="${y(f.properties[field])}" r="3.8" fill="${categories[f.properties[classField]]}" stroke="#dedede" stroke-width=".6"><title>${esc(f.properties.name)} · ${tr('Tourist homes per 1,000 dwellings','每千套住宅的旅游住房登记')}: ${fmt(f.properties.hutIntensity)} · ${change?tr('Rent change','租金涨幅'):tr('Rent (€ / m² / month)','租金（欧元/平方米/月）')}: ${fmt(f.properties[field])}${change?'%':''}</title></circle>`).join('')}<text class="chart-axis-title" x="${(left+right)/2}" y="250" text-anchor="middle">${tr('Tourist-home registrations per 1,000 dwellings · 2026','旅游住房登记（条/千套住宅，2026）')}</text>`;
        const labels = {both:tr('Both high','两项都高'),tourism:tr('Tourist homes high only','仅旅游住房较多'),rent:change?tr('Rent growth high only','仅租金涨幅较大'):tr('Rent high only','仅租金较高'),neither:tr('Neither high','两项都不高')};
        return `<figcaption>${caption}</figcaption><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(caption+' · '+yTitle)}">${svg}</svg><div class="chart-key">${Object.entries(labels).map(([k,label])=>`<span><i style="background:${categories[k]}"></i>${label}</span>`).join('')}</div><p class="chart-reading">${tr('Each dot is one of 66 comparable neighbourhoods. Dashed lines mark the top-quarter cut-offs; colours match the map.', '每个点代表一个街区，共66个。虚线划出排名前四分之一的范围；点的颜色与地图一致。')}</p>`;
    }
    else if (id === 'C05') {
        const rows = summary.platformDates;
        const max = Math.max(...rows.map((r: any) => r.records));
        svg = rows.map((r: any, i: number) => `<rect x="${25 + i * 85}" y="${125 - r.records / max * 90}" width="38" height="${r.records / max * 90}" fill="${i === snapshot ? '#df9c71' : '#aaa'}"/><text x="${44 + i * 85}" y="${117 - r.records / max * 90}" text-anchor="middle">${fmt(r.records, 0)}</text><text x="${44 + i * 85}" y="148" text-anchor="middle">${r.snapshot.slice(0, 7).replace('-', '.')}</text>`).join('');
        const pair = summary.charts.platformTransitions.find((p: any) => p.pairIndex === snapshot);
        caption = tr('Airbnb listings · four citywide observations', 'Airbnb 房源数 · 全市四次观测');
        const selectedDate = rows[snapshot].snapshot.slice(0,7).replace('-','.');
        const note = pair ? tr(`Map: ${selectedDate}. Compared with the previous observation: ${fmt(pair.newlyObserved,0)} listings appeared and ${fmt(pair.notReobserved,0)} were no longer seen.`, `地图当前显示 ${selectedDate}。与上期相比，${fmt(pair.newlyObserved,0)} 条房源本期出现，${fmt(pair.notReobserved,0)} 条上期房源本期未出现。`) : tr(`Map: ${selectedDate}, the first observation. This is the starting point for later comparisons.`, `地图当前显示 ${selectedDate}，这是首次观测，作为后续比较的起点。`);
        return `<figcaption>${caption}</figcaption><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}">${svg}</svg><p class="chart-reading">${note}</p>`;
    }
    return `<figcaption>${caption}</figcaption><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(caption)}">${svg}</svg>`;
}
function renderDiagrams() { document.querySelectorAll<HTMLElement>('[data-diagram]').forEach(el => { const d = content.diagrams?.find((d: any) => d.id === el.dataset.diagram); const events = d?.events || d?.steps || []; const label = (x: any) => typeof x === 'object' ? x?.[lang] : x; el.innerHTML = `<div class="timeline">${events.map((e: any, i: number) => `<div class="event ${['not_verified', 'future_target', 'pending', 'unverified', 'future'].includes(e.status) ? 'pending' : ''}"><b>${esc(e.date || String(i + 1).padStart(2, '0'))}</b><span>${esc(label(e.label) || label(e.text) || label(e.title) || '')}${e.status === 'not_verified' ? ' · ' + tr('not yet verified', '尚未证实') : ''}</span></div>`).join('')}</div>`; }); }
function blend(a: string, b: string, t: number) { t = Math.max(0, Math.min(1, t)); return '#' + [1, 3, 5].map(i => Math.round(parseInt(a.slice(i, i + 2), 16) * (1 - t) + parseInt(b.slice(i, i + 2), 16) * t).toString(16).padStart(2, '0')).join(''); }
function flatPolygons(g: any): any[] { return g.type === 'GeometryCollection' ? g.geometries.flatMap(flatPolygons) : g.type === 'MultiPolygon' ? g.coordinates : g.type === 'Polygon' ? [g.coordinates] : []; }
function staticColor(m: string, p: Record<string, any>) {
    if (m === 'M08' || m === 'M09')
        return categories[p[m === 'M08' && comparison === 'change' ? 'changeClass' : 'overlapClass']] || '#222222';
    const field = themeField[m];
    if (!field)
        return '#303030';
    const valid = m === 'M05' ? 'validRent2025' : m === 'M06' ? 'validRentChange' : m === 'M07' ? 'validContractActivity' : 'comparable';
    if (p.comparable === false || p[valid] === false || typeof p[field] !== 'number')
        return '#222222';
    const [lo, hi] = extent(field), v = p[field];
    if (m === 'M06') {
        const lim = Math.max(Math.abs(lo), Math.abs(hi), 1);
        return v < 0 ? blend('#444444', '#d8d8d8', (v + lim) / lim) : blend('#d8d8d8', '#bb4436', v / lim);
    }
    return blend(m === 'M07' ? '#333333' : '#79746f', m === 'M05' ? '#bf483e' : m === 'M07' ? '#dddddd' : '#dc955e', (v - lo) / (hi - lo || 1));
}
function fallback() {
    simpleMap = true;
    const el = $('#map-fallback');
    el.hidden = false;
    $('#map').hidden = true;
    const m = currentTheme();
    const caseId = active === 11 && !exploring ? '07' : String(caseList()[caseIndex]?.id ?? '10');
    const caseFeature = neighbourhoods.features.find(f => f.properties.id === caseId);
    const box = m === 'M09' && caseFeature ? bounds(caseFeature.geometry) : m === 'M01' ? bounds(cityContext.features.find(f=>f.properties.kind==='city')!.geometry) : [[2.052, 41.325], [2.229, 41.455]];
    const lo = box[0], hi = box[1], cos = Math.cos(41.4 * Math.PI / 180), scale = Math.min((mobile() ? innerWidth * .9 : innerWidth * .55) / ((hi[0] - lo[0]) * cos), innerHeight * .72 / (hi[1] - lo[1]));
    const project = (p: number[]) => [(p[0] - (lo[0] + hi[0]) / 2) * cos * scale + innerWidth * (mobile() ? .50 : .65), ((lo[1] + hi[1]) / 2 - p[1]) * scale + innerHeight * .48];
    const path = (g: any) => flatPolygons(g).map((p: any) => p.map((r: any) => r.map((pt: number[], i: number) => (i ? 'L' : 'M') + project(pt).join(',')).join(' ') + 'Z').join(' ')).join(' ');
    let shapes = neighbourhoods.features.map(f => { const highlighted = (exploring && f.properties.id === selected) || (m === 'M09' && f.properties.id === caseId); return `<path d="${path(f.geometry)}" fill="${staticColor(m, f.properties)}" fill-rule="evenodd" stroke="${highlighted ? '#f0b396' : m === 'M01' ? '#b47857' : '#777'}" stroke-width="${highlighted ? 2 : .6}"><title>${esc(f.properties.name)}</title></path>`; }).join('');
    if (m === 'M01') shapes += cityContext.features.map(f=>`<path d="${path(f.geometry)}" fill="none" stroke="${f.properties.kind==='city'?'#eea275':'#d28b61'}" stroke-width="${f.properties.kind==='city'?2.2:1.2}"><title>${esc(f.properties.name)}</title></path>`).join('');
    if (m === 'M02')
        shapes += hut.features.map(f => { const p = project(f.geometry.coordinates); return `<circle cx="${p[0]}" cy="${p[1]}" r="1.3" fill="#efb894" opacity=".65"/>`; }).join('');
    if (m === 'M03' || m === 'M10') {
        const t = m === 'M03' ? 3 : snapshot, share = m === 'M03' && platformMode === 'share';
        const key = m === 'M10' && ['new', 'lost'].includes(observationMode) ? (t > 0 ? observationMode + t : 'none') : m === 'M03' && ['entire', 'short'].includes(platformMode) ? platformMode + t : 'n' + t;
        const max = Math.max(...grid.features.flatMap(f => [0, 1, 2, 3].map(j => Number(f.properties['n' + j]) || 0)), 1);
        shapes += grid.features.map(f => { const p = f.properties, c = project(centroid(f.geometry)); return share ? `<path d="${path(f.geometry)}" fill="${typeof p['share' + t] === 'number' ? blend('#777777', '#d77943', p['share' + t] / 100) : '#222222'}" stroke="#555" stroke-width=".5"/>` : (p[key] > 0 ? `<circle cx="${c[0]}" cy="${c[1]}" r="${22 * Math.sqrt(p[key] / max)}" fill="${observationMode === 'lost' && m === 'M10' ? '#cb6254' : '#e4ad83'}" opacity=".8"/>` : ''); }).join('');
    }
    el.innerHTML = `<svg viewBox="0 0 ${innerWidth} ${innerHeight}" role="img" aria-label="${esc(themeTitle(m) + ' · ' + tr('simplified evidence map', '简洁证据地图'))}">${shapes}</svg>`;
    simpleMapStatus();
}
start();
