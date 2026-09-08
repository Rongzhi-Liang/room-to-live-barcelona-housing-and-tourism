"""Build the frozen bilingual Barcelona story from explicit repository inputs.

Uses Python's standard library. Performs no network request and changes no input.
All relative input/output paths resolve against --repo; only --out is written.
The story's scientific definitions and documented policy evidence are retained.
"""
from pathlib import Path
import argparse, copy, hashlib, json, math, os, re

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path('.'), help='Repository root for path resolution and provenance.')
parser.add_argument('--public-root', type=Path, required=True, help='Analysis directory containing summary.json and neighbourhoods.geojson.')
parser.add_argument('--template', type=Path, required=True, help='Read-only bilingual editorial template.')
parser.add_argument('--sources', type=Path, required=True, help='Read-only source registry; object with sources or a source array.')
parser.add_argument('--places', type=Path, required=True, help='Read-only T04 public evidence GeoJSON.')
parser.add_argument('--metadata', type=Path, required=True, help='Read-only frozen HUT CKAN package metadata.')
parser.add_argument('--out', type=Path, required=True, help='Directory for generated editorial, bindings, case decision and validation.')
args=parser.parse_args()
REPO=args.repo.resolve()
if not REPO.is_dir():
    parser.error('--repo must be an existing directory')

def resolve(value):
    return (value if value.is_absolute() else REPO/value).resolve()

PUBLIC=resolve(args.public_root)
SUMMARY=PUBLIC/'summary.json'
GEOMETRY=PUBLIC/'neighbourhoods.geojson'
TEMPLATE=resolve(args.template)
SOURCES=resolve(args.sources)
PLACES=resolve(args.places)
META=resolve(args.metadata)
OUT=resolve(args.out)
all_inputs=[SUMMARY,GEOMETRY,META,TEMPLATE,SOURCES,PLACES]
output_names=['editorial.resolved.json','bindings.json','case_selection.json','editorial_validation.json']
for input_path in all_inputs:
    if not input_path.is_file():
        parser.error('Missing input: '+str(input_path))
for name in output_names:
    destination=OUT/name
    if destination.is_symlink() or destination.resolve() in all_inputs:
        parser.error('Output must not overwrite or symlink to an input: '+str(destination))
input_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in all_inputs}
outputs={}
summary=json.loads(SUMMARY.read_text(encoding='utf-8'))
features=json.loads(GEOMETRY.read_text(encoding='utf-8'))['features']
neighbourhoods={f['properties']['id']:f['properties'] for f in features}
city={r['year']:r for r in summary['charts']['cityRent']}
level=summary['overlap']['level']
change=summary['overlap']['change']
template=json.loads(TEMPLATE.read_text(encoding='utf-8'))
sources=json.loads(SOURCES.read_text(encoding='utf-8'))
if isinstance(sources,list):
    sources={'sources':sources}
source_ids={r['source_id'] for r in sources['sources']}
bindings={}

def path(p):
    return Path(os.path.relpath(p.resolve(),REPO)).as_posix()

def reference(file,selector,value):
    return {'file':path(file),'selector':selector,'value':value}

def rs(selector,value):
    return reference(SUMMARY,selector,value)

def rn(i,fields):
    return reference(GEOMETRY,f'features[properties.id={i}].properties', {f:neighbourhoods[i][f] for f in fields})

def rq(i):
    s=next(r for r in sources['sources'] if r['source_id']==i)
    return reference(SOURCES,f'sources[source_id={i}]',{'url':s['url'],'date':s['date'],'event_date':s['event_date'],'status':s['status']})

def bind(key,en,zh,refs,calculation=None):
    bindings[key]={'en':en,'zh':zh,'sources':refs,'calculation':calculation,'checked':True}

f1=lambda v:f'{v:.1f}'
f2=lambda v:f'{v:.2f}'
fi=lambda v:f'{int(v):,}'
hut_resource=next(r for r in json.loads(META.read_text(encoding='utf-8'))['result']['resources'] if r['id']=='b32fa7f6-d464-403b-8a02-0292a64883bf')
assert hut_resource['last_modified'].startswith('2026-05-21')
bind('hut_reference_date','21 May 2026','2026 年 5 月 21 日', [reference(META,'result.resources[id=b32fa7f6-d464-403b-8a02-0292a64883bf].last_modified',hut_resource['last_modified'])])

bind('city_rent_path',
 f"The average agreed rent moved from €{f2(city[2019]['rentM2'])}/m²/month in 2019 to €{f2(city[2021]['rentM2'])} in 2021, then €{f2(city[2025]['rentM2'])} in 2025.",
 f"全市新签租约的平均租金从 2019 年的每平方米每月 {f2(city[2019]['rentM2'])} 欧元，降至 2021 年的 {f2(city[2021]['rentM2'])} 欧元，再升至 2025 年的 {f2(city[2025]['rentM2'])} 欧元。",
 [rs('charts.cityRent[year=2019|2021|2025]',[city[y] for y in [2019,2021,2025]])])

latest_index=max(r['snapshotIndex'] for r in summary['platformDates'])
latest=next(r for r in summary['platformDates'] if r['snapshotIndex']==latest_index)
composition=[r for r in summary['charts']['platformComposition'] if r['snapshotIndex']==latest_index]
entire=sum(r['records'] for r in composition if r['roomType']=='Entire home/apt')
long_stay=sum(r['records'] for r in composition if r['stayBand'] in ['31-89','90+'])
unknown_stay=sum(r['records'] for r in composition if r['stayBand']=='unknown')
assert sum(r['records'] for r in composition)==latest['records']
bind('platform_composition',
 f"Entire homes account for {fi(entire)} of {fi(latest['records'])} listings ({f1(100*entire/latest['records'])}%); {fi(long_stay)} advertise a minimum stay of at least 31 nights.",
 f"{fi(latest['records'])} 条房源中，{fi(entire)} 条为整套住房，占 {f1(100*entire/latest['records'])}%；按最短入住要求统计，{fi(long_stay)} 条房源要求至少预订 31 晚。",
 [rs('charts.platformComposition[snapshotIndex=3]',composition),rs('platformDates[snapshotIndex=3]',latest)],
 {'entire_share_percent':100*entire/latest['records'],'long_minimum_count':long_stay,'unknown_minimum_count':unknown_stay,'definition':'Minimum nights are advertised conditions; room-type and stay categories overlap.'})
bind('platform_reference_date',latest['snapshot'],latest['snapshot'],[rs('platformDates[snapshotIndex=3].snapshot',latest['snapshot'])])

a=neighbourhoods['10']; b=neighbourhoods['40']; gracia=neighbourhoods['31']; sarria=neighbourhoods['23']; gotic=neighbourhoods['02']; dreta=neighbourhoods['07']
assert a['thresholdStable'] and b['thresholdStable']
first=summary['cases']['candidates'][0]
assert first['a']=='10' and first['b']=='40' and first['rank']==1
assert summary['cases']['status']=='eligible_pair_selected_with_public_place_evidence'
assert [r['id'] for r in summary['cases']['selected']]==['10','40']
bind('hut_count_intensity_contrast',
 f"Sant Antoni has fewer registrations than la Vila de Gràcia ({fi(a['hutCount'])} versus {fi(gracia['hutCount'])}), but greater intensity: {f1(a['hutIntensity'])} versus {f1(gracia['hutIntensity'])} per 1,000 homes.",
 f"Sant Antoni 有 {fi(a['hutCount'])} 条登记，少于 la Vila de Gràcia 的 {fi(gracia['hutCount'])} 条；但换算到每千套住宅，前者为 {f1(a['hutIntensity'])} 条，后者为 {f1(gracia['hutIntensity'])} 条。",
 [rn(i,['hutCount','housing2026','hutIntensity']) for i in ['10','31']])
bind('rent_level_contrast',
 f"Sarrià averaged €{f2(sarria['rent2025'])}/m²/month; in Sant Antoni, the figure was €{f2(a['rent2025'])}.",
 f"Sarrià 的平均租金为每平方米每月 {f2(sarria['rent2025'])} 欧元，Sant Antoni 则为 {f2(a['rent2025'])} 欧元。",
 [rn(i,['rent2025','contracts2025','validRent2025']) for i in ['23','10']])
bind('rent_change_contrast',
 f"Montbau's average rose {f1(b['rentChange'])}%, compared with {f1(sarria['rentChange'])}% in Sarrià, despite Sarrià's higher 2025 price.",
 f"Montbau 的平均租金上涨了 {f1(b['rentChange'])}%，Sarrià 上涨了 {f1(sarria['rentChange'])}%；到 2025 年，租金仍然是 Sarrià 更高。",
 [rn(i,['rent2022','rent2025','rentChange','contracts2022','contracts2025','validRentChange']) for i in ['40','23']])
bind('contract_activity_contrast',
 f"El Barri Gòtic recorded {f1(gotic['contractIntensity'])} contracts per 1,000 homes, against {f1(b['contractIntensity'])} in Montbau. Citywide, the total fell from {fi(city[2022]['contracts'])} in 2022 to {fi(city[2025]['contracts'])} in 2025.",
 f"el Barri Gòtic 每千套住宅记录 {f1(gotic['contractIntensity'])} 份新合同，Montbau 为 {f1(b['contractIntensity'])} 份。全市合同数则从 2022 年的 {fi(city[2022]['contracts'])} 份降至 2025 年的 {fi(city[2025]['contracts'])} 份。",
 [rn(i,['contractIntensity','contracts2025','housing2025']) for i in ['02','40']]+[rs('charts.cityRent[year=2022|2025].contracts',{str(y):city[y]['contracts'] for y in [2022,2025]})])
bind('overlap_finding',
 f"Among {level['sampleN']} comparable neighbourhoods, the highest quarter for tourist-home intensity contains {level['tourismHigh']} neighbourhoods. Of those, {level['intersection']} are also in the highest rent quarter, while only {change['intersection']} is in the quarter with the fastest 2022–2025 rent growth.",
 f"在可比较的 {level['sampleN']} 个街区中，旅游住房登记强度最高的四分之一包括 {level['tourismHigh']} 个街区。其中，{level['intersection']} 个同时位于租金最高的四分之一；若比较 2022—2025 年租金涨幅，同时进入涨幅最高四分之一的只有 {change['intersection']} 个。",
 [rs('overlap.level',level),rs('overlap.change',change)])
bind('counterexample_finding',
 "Sarrià is in the high-rent group with relatively few registrations; Sant Antoni has high registration intensity without top-quarter rent.",
 "Sarrià 属于高租金组，却不属于旅游住房高集中组；Sant Antoni 的情况恰好相反。",
 [rn(i,['hutIntensity','rent2025','overlapClass']) for i in ['23','10']],
 {'rule':'Quarter-based classes within the common sample; not claims of absolute affordability.'})
bind('case_a_name',a['name'],a['name'],[rn('10',['name'])])
bind('case_b_name',b['name'],b['name'],[rn('40',['name'])])
bind('case_a_finding',
 f"2025 new-lease rent averaged €{f2(a['rent2025'])}/m²/month; the 2026 register contains {f1(a['hutIntensity'])} tourist-home registrations per 1,000 homes",
 f"2025 年新签租约的平均租金为每平方米每月 {f2(a['rent2025'])} 欧元；2026 年每千套住宅有 {f1(a['hutIntensity'])} 条旅游住房登记",
 [rn('10',['rent2025','hutIntensity','contracts2025','overlapClass'])])
bind('case_b_finding',
 f"the corresponding rent was €{f2(b['rent2025'])}/m²/month, with no tourist-home entries in the adopted 2026 register",
 f"同期租金为每平方米每月 {f2(b['rent2025'])} 欧元，本次采用的 2026 年登记表中没有旅游住房记录",
 [rn('40',['rent2025','hutCount','hutPending','hutIntensity','contracts2025','overlapClass'])])
bind('case_local_evidence',
 "Sant Antoni's association asked in 2017 for residents to be able to remain. Montbau's association recalls a neighbourhood planned for postwar housing needs.",
 "Sant Antoni 居民协会在 2017 年要求居民能够留下；Montbau 居民协会则记述了街区为回应战后住房需求而规划建设的历史。",
 [rq('sant_antoni_association'),rq('montbau_association')])
bind('case_selection_note',
 f"First-ranked eligible pair; rent gap €{f2(first['rentGap'])}/m²/month. Both classifications persist across 20%, 25% and 33% high-value definitions.",
 f"数值排序首位的合格组合；租金差为每平方米每月 {f2(first['rentGap'])} 欧元。两地分类在 20%、25%、33% 高值定义下均保持。",
 [rs('cases.candidates[rank=1]',first),rs('cases.rule',summary['cases']['rule'])],
 {'source_availability':'Both numerical first-ranked places have verified local sources; no reranking by reputation or material availability.','interpretation':'Descriptive comparison, not a matched causal design; stability here refers only to the HUT × 2025-rent class across three thresholds.'})
transition=summary['charts']['platformTransitions'][-1]
first_platform=min(summary['platformDates'],key=lambda row:row['snapshotIndex'])
platform_decline=first_platform['records']-latest['records']
bind('platform_observation_finding',
 f"Observed Airbnb listings fell from {fi(first_platform['records'])} in September 2025 to {fi(latest['records'])} in the June 2026 batch, a decline of {fi(platform_decline)} ({f1(100*platform_decline/first_platform['records'])}%). Between March and the June batch, {fi(transition['notReobserved'])} listing IDs were no longer observed, while {fi(transition['newlyObserved'])} appeared that were absent in March.",
 f"采集到的 Airbnb 房源从 2025 年 9 月的 {fi(first_platform['records'])} 条，降至 2026 年 6 月批次的 {fi(latest['records'])} 条，减少 {fi(platform_decline)} 条（{f1(100*platform_decline/first_platform['records'])}%）。只看最后两期，3 月出现的 {fi(transition['notReobserved'])} 个房源编号在 6 月批次中未再出现，同时又出现了 3 月没有的 {fi(transition['newlyObserved'])} 个编号。",
 [rs('charts.platformTransitions[pairIndex=3]',transition),rs('platformDates[snapshotIndex=0|3]',[first_platform,latest])],
 {'identities':['reobserved + newlyObserved = laterCount','reobserved + notReobserved = earlierCount'],
  'period_decline':platform_decline,'period_decline_percent':100*platform_decline/first_platform['records'],
  'nonadditivity':'NewlyObserved is relative to the preceding snapshot; some IDs return after a gap.'})
assert transition['reobserved']+transition['newlyObserved']==transition['laterCount']
assert transition['reobserved']+transition['notReobserved']==transition['earlierCount']
bind('monitoring_finding',
 "La Vila de Gràcia ranks in the top quarter for both tourist-home intensity and rent. Sarrià has high rents without high tourist-home intensity; Montbau stands out for rent growth.",
 "la Vila de Gràcia 的旅游住房登记和租金都处于高值组；Sarrià 租金高，却不属于旅游住房高集中组；Montbau 的突出特征则是租金上涨较快。",
 [rn(i,['overlapClass','changeClass','hutIntensity','rent2025','rentChange','thresholdStable']) for i in ['31','23','40']])
bind('closing_findings',
 f"Of the {level['tourismHigh']} neighbourhoods with the highest tourist-home registration intensity, {level['intersection']} are also among the most expensive, but only {change['intersection']} is among those with the fastest recent rent growth. Similar rents also coexist with very different tourist-home concentrations, as Sant Antoni and Montbau show.",
 f"旅游住房登记最集中的 {level['tourismHigh']} 个街区中，{level['intersection']} 个也是租金最高的街区，只有 {change['intersection']} 个进入近期涨幅最高的一组。Sant Antoni 与 Montbau 的对照还表明，相近的租金可以对应非常不同的旅游住房集中程度。",
 [rs('overlap.level',level),rs('overlap.change',change),rn('10',['rent2025','hutIntensity']),rn('40',['rent2025','hutIntensity'])],
 {'robustness':'The number of high-value intersections changes with thresholds and baseline years; rank association is stronger for rent levels than for growth in the tested scenarios. No causal estimate is implied.'})

decision={'case_a':'10','case_b':'40','numeric_rank':first['rank'],'numeric_rule':summary['cases']['rule'],'rent_gap_limit':summary['cases']['rentGapLimit'],'observed_pair':first,'source_ids':['sant_antoni_association','montbau_association'],'selection_status':'selected_after_place_specific_source_check','selection_basis':'The numerical first-ranked eligible pair has direct neighbourhood sources. The source review does not change its numerical rank.','evidence_role':'Dated local advocacy and housing history contextualise the pair; they do not explain the cause of current prices.','analysis_selection_status':summary['cases']['status']}
outputs['case_selection.json']=json.dumps(decision,ensure_ascii=False,indent=2)+'\n'

def subst(text,lang):
    return re.sub(r'\{\{(\w+)\}\}',lambda m:bindings[m.group(1)][lang],text)

resolved=copy.deepcopy(template)
for chapter in resolved['chapters']:
    for key in ['title','body','eyebrow','microNote']:
        for lang,text in chapter.get(key,{}).items():
            chapter[key][lang]=subst(text,lang)
    chapter['requiredFields']=[]

# The template is the sole source of finished chapter prose. Keep computed
# facts in bindings, so rebuilding cannot restore obsolete wording.
for c in resolved['chapters']:
    for key in ['body','microNote']:
        if key in c:
            c[key]['zh']=re.sub(r'([。；]) +',r'\1',c[key]['zh'])

level_scenarios=[r for r in summary['sensitivity']['overlap'] if r['dimension']=='level' and r['scenario'].startswith('share_')]
change_scenarios=[r for r in summary['sensitivity']['overlap'] if r['dimension']=='change' and r['scenario'].startswith('share_')]
baseline_scenarios=[r for r in summary['sensitivity']['overlap'] if r['scenario'] in ['base_2019','base_2023']]
baseline_en='; '.join(f"{r['baseYear']}: {r['intersection']}" for r in baseline_scenarios)
baseline_zh='；'.join(f"{r['baseYear']} 年：{r['intersection']} 个" for r in baseline_scenarios)
resolved['methodsEditorial']['comparison']={
 'en':f"The main high-value definition is the upper quarter of the common sample ({level['sampleN']} neighbourhoods), with a {level['minimumContracts']}-contract quality threshold and confirmed geographical comparability. HUT intensity and rent-level ranks have Spearman correlation {level['spearman']:.2f}; the correlation with 2022–2025 rent change is {change['spearman']:.2f}. At high-value shares of 20%, 25% and 33%, the rent-level intersection is respectively {', '.join(str(r['intersection']) for r in level_scenarios)} neighbourhoods; the growth intersection is {', '.join(str(r['intersection']) for r in change_scenarios)}. Alternative growth baselines give these intersections ({baseline_en}). The precise high-value count is sensitive to the definition. The results establish spatial association, not the causal effect of tourist homes or policy.",
 'zh':f"主要高值定义为共同样本（{level['sampleN']} 个街区）的最高四分之一，采用 {level['minimumContracts']} 份合同的质量门槛，并要求统计地域可比。HUT 强度与租金水平的 Spearman 秩相关为 {level['spearman']:.2f}，与 2022—2025 年租金变化的相关为 {change['spearman']:.2f}。高值比例分别采用 20%、25%、33% 时，租金水平的重合街区数为 {'、'.join(str(r['intersection']) for r in level_scenarios)}，增幅的重合数为 {'、'.join(str(r['intersection']) for r in change_scenarios)}；采用其他增幅基期得到的重合数量为（{baseline_zh}）。高值数量对定义敏感；结果描述空间关联，不是旅游住房或政策的因果效应。",
 'sourceIds':['hut_data','rent_data','cadastre_data']}
resolved['methodsEditorial']['caseSelection']={
 'en':f"Sant Antoni and Montbau are the first-ranked pair among {summary['cases']['candidateCount']} candidates. The rule allows a rent gap no greater than half the common-sample standard deviation (€{f2(summary['cases']['rentGapLimit'])}/m²/month), requires opposite HUT high-value groups, and prioritises threshold-stable classifications, larger HUT gaps, then smaller rent gaps. Their 2025 contract counts are {fi(a['contracts2025'])} and {fi(b['contracts2025'])}. The local-source check retained this first-ranked pair. The comparison is descriptive, and their historical records do not establish the cause of current rents.",
 'zh':f"Sant Antoni 与 Montbau 是 {summary['cases']['candidateCount']} 组候选中数值排序第一的组合。规则允许租金差不超过共同样本标准差的一半（每平方米每月 {f2(summary['cases']['rentGapLimit'])} 欧元），要求 HUT 高值分组相反，并优先采用阈值分类稳定、HUT 差较大、租金差较小的组合。两地 2025 年合同数分别为 {fi(a['contracts2025'])} 与 {fi(b['contracts2025'])}。地方案例来源核查后保留数值首位组合。这是描述性比较，历史材料不证明当前租金差异的原因。",
 'sourceIds':['sant_antoni_association','montbau_association','rent_data','hut_data']}
resolved['methodsEditorial']['policyStatus']={
 'en':"November 2028 remains the city's policy target. The Catalan decree includes a conditional extension application mechanism, and a court ruling on the decree does not resolve every later implementation dispute. The 2024 and 2026 rental-rule changes are contemporaneous context. Historical organisational statements about unregulated seasonal rental must be read at their publication date.",
 'zh':"2028 年 11 月仍是市府政策目标。加泰罗尼亚法令包含须符合条件的延长申请机制，对法令的法院裁决也不等于所有后续实施争议均已解决。2024 与 2026 年的租赁规则变化属于同期背景；历史组织声明中关于季节租赁规制的表述，应放回其发表时间理解。",
 'sourceIds':['policy_2026','decree_2023','court_2025','rent_regulation_2024','rental_rules_2026']}
resolved['methodsEditorial']['caseStatus']={
 'en':"Diputació 354 is shown at neighbourhood scale, although the official programme identifies its public address. The rules document a mix of completed and continuing habitability works. A public draw is documented for 30 March 2026. The register page forecasts completion in 2026; signed leases and occupancy have not been independently established. Base rent excludes approximately €35 monthly stated charges and utilities. This is one public-acquisition pathway, not a universal mechanism for HUT conversion.",
 'zh':"Diputació 354 按街区范围显示，尽管官方项目已明确公开地址。分配规则记载部分居住条件整修完成、部分仍在进行；2026 年 3 月 30 日的公开抽签已有记录。登记页预计 2026 年完成；尚未独立核实最终租约签署与入住。基础租金另有约每月 35 欧元规定费用和公用事业支出。这是一条公共收购路径，并非所有 HUT 转换的统一机制。",
 'sourceIds':['allocation_bases','allocation_resolution','allocation_draw','allocation_detail']}

resolved['caseIds']=['10','40']
text=json.dumps(resolved,ensure_ascii=False,indent=2)
assert '{{' not in text and '}}' not in text
assert len(resolved['chapters'])==14
assert all(v in source_ids for c in resolved['chapters'] for v in c['sourceIds'])
assert len(resolved['objective']['en'].split())<=100
assert len(resolved['storyIntention']['en'].split())<=100
outputs['editorial.resolved.json']=text+'\n'
record={'input_files':[{'file':path(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in all_inputs], 'analysis_case_status':summary['cases']['status'],'bindings':bindings,'case_selection':decision,'rendered_word_counts':{c['id']:len(c['body']['en'].split()) for c in resolved['chapters']},'unresolved_tokens':0,'objective_words':len(resolved['objective']['en'].split()),'story_intention_words':len(resolved['storyIntention']['en'].split()),'source_references_resolve':True}
chapter_binding_keys={
 '01':[], '02':['hut_reference_date'], '03':['city_rent_path'],
 '04':['platform_composition','platform_reference_date'],
 '05':['hut_count_intensity_contrast'], '06':['rent_level_contrast'],
 '07':['rent_change_contrast'], '08':['contract_activity_contrast'],
 '09':['overlap_finding','counterexample_finding'],
 '10':['case_a_name','case_b_name','case_a_finding','case_b_finding'],
 '11':['platform_observation_finding'], '12':[],
 '13':['monitoring_finding'], '14':['closing_findings']}
record['resolved_field_provenance']={
 f'chapters[id={c["id"]}].body|microNote':{
     'binding_keys':chapter_binding_keys[c['id']],
     'qualitative_or_data_sources':[rq(i) for i in c['sourceIds']],
     'copy_rule':'English and Chinese express the same finding; displayed values use the rounding recorded in each named binding.'}
 for c in resolved['chapters']}
record['resolved_field_provenance']['methodsEditorial.comparison']={
 'sources':[rs('overlap.level',level),rs('overlap.change',change),
            rs('sensitivity.overlap[scenario=share_*|base_2019|base_2023]',level_scenarios+change_scenarios+baseline_scenarios)],
 'rounding':'Spearman correlations rounded to two decimals; counts exact.'}
record['resolved_field_provenance']['methodsEditorial.caseSelection']={
 'sources':[rs('cases',{k:v for k,v in summary['cases'].items() if k!='candidates'}),rs('cases.candidates[rank=1]',first)],
 'rounding':'Rent-gap limit rounded to two decimals; contract counts exact.'}
record['resolved_field_provenance']['chapters[id=12].body.numeric_facts']={
 'sources':[reference(SOURCES,'sources[source_id=allocation_bases].paraphrase|page|limits',
            {'homes':22,'base_rent_eur_m2_month':10.65,'minimum_lease_years':7,'page':'3'}),
            reference(SOURCES,'sources[source_id=allocation_draw].event_date','2026-03-30')],
 'event_state':'Allocation rules and draw are documented; lease signing and occupancy are not claimed.'}
for d in resolved['diagrams']:
    for row in d.get('events',d.get('steps',[])):
        record['resolved_field_provenance'][f'diagrams[id={d["id"]}].items[id={row.get("id",row.get("date"))}]']={
            'sources':[rq(i) for i in row['sourceIds']],
            'status':row['status']}
outputs['bindings.json']=json.dumps(record,ensure_ascii=False,indent=2)+'\n'

# Validate the exact delivery, including sources used outside chapter text.
references=[]
def collect_references(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if k=='sourceIds': references.extend(v)
            else: collect_references(v)
    elif isinstance(value,list):
        for v in value: collect_references(v)
collect_references(resolved)
assert all(i in source_ids for i in references)
geo=json.loads(PLACES.read_text(encoding='utf-8'))
assert geo['type']=='FeatureCollection' and len(geo['features'])==7
assert len({f['id'] for f in geo['features']})==len(geo['features'])
coordinate_count=0
for f in geo['features']:
    assert f['geometry']['type'] in ['Polygon','MultiPolygon']
    assert all(isinstance(v,(str,int,float,bool)) or v is None for v in f['properties'].values())
    assert f['properties']['source_id'] in source_ids
    assert f['properties']['location_precision'] in ['city','neighbourhood']
    for i in f['properties'].get('supporting_source_ids','').split('|'):
        assert not i or i in source_ids
    polys=f['geometry']['coordinates'] if f['geometry']['type']=='MultiPolygon' else [f['geometry']['coordinates']]
    for polygon in polys:
        for ring in polygon:
            assert len(ring)>=4 and ring[0]==ring[-1]
            for coordinate in ring:
                assert len(coordinate)==2 and all(math.isfinite(v) for v in coordinate)
                assert -180<=coordinate[0]<=180 and -90<=coordinate[1]<=90
                coordinate_count+=1
assert len({c['map'] for c in resolved['chapters']})==10
assert all(c['body']['en'].strip() and c['body']['zh'].strip() for c in resolved['chapters'])
assert all(c['title']['en'].strip() and c['title']['zh'].strip() for c in resolved['chapters'])
current_summary_hash=hashlib.sha256(SUMMARY.read_bytes()).hexdigest()
assert current_summary_hash==record['input_files'][0]['sha256']
validation={
 'status':'editorial_bound_and_checked','chapters':14,'map_themes':10,
 'source_count':len(source_ids),'binding_count':len(bindings),'qualitative_features':len(geo['features']),
 'qualitative_geometry_types':sorted({f['geometry']['type'] for f in geo['features']}),
 'qualitative_coordinate_pairs_checked':coordinate_count,
 'geometry_scope':'City and neighbourhood polygons only; no individual-household points.',
 'geometry_validation':'Finite WGS84 ranges, closed rings, unique feature IDs and scalar Mapbox properties checked. Geographical topology is inherited from the validated official source; no independent rendering claim.',
 'all_source_references_resolve':True,'unresolved_tokens':0,
 'bilingual_chapters_complete':True,'english_body_word_counts':record['rendered_word_counts'],
 'objective_words':record['objective_words'],'story_intention_words':record['story_intention_words'],
 'case_ids':['10','40'],'case_selection_status':summary['cases']['status'],
 'analysis_summary_sha256':current_summary_hash,
 'pending_editorial_work':[],
 'evidence_boundaries':[
     'Direct opening of the February 2026 policy PDF remains restricted; the official indexed target paragraph is checked and full-document review is not claimed.',
     'Lease signing and occupancy at Diputació 354 remain unverified and are presented as the next outcomes to follow.',
     'Local association evidence supplies dated context, not a causal explanation of present rents.'
 ],
 'input_asset_hashes':{'sources.json':hashlib.sha256(SOURCES.read_bytes()).hexdigest(),'qualitative.geojson':hashlib.sha256(PLACES.read_bytes()).hexdigest()},
 'delivery_hashes':{name:hashlib.sha256(value.encode('utf-8')).hexdigest() for name,value in outputs.items()}}
outputs['editorial_validation.json']=json.dumps(validation,ensure_ascii=False,indent=2)+'\n'
for input_path in all_inputs:
    if hashlib.sha256(input_path.read_bytes()).hexdigest()!=input_hashes[str(input_path)]:
        raise RuntimeError('Input changed while building: '+str(input_path))
OUT.mkdir(parents=True,exist_ok=True)
for name,value in outputs.items():
    destination=OUT/name
    if destination.is_symlink():
        raise RuntimeError('Refusing symlink output: '+str(destination))
    with destination.open('w',encoding='utf-8',newline='\n') as handle:
        handle.write(value)
print(json.dumps({k:record[k] for k in ['analysis_case_status','rendered_word_counts','unresolved_tokens','objective_words','story_intention_words','source_references_resolve']},ensure_ascii=False))
