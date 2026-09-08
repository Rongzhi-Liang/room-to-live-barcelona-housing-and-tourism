#!/usr/bin/env python3
"""Independently check public interfaces and compare two completed builds."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile7(values, probability):
    values = sorted(values)
    at = (len(values) - 1) * probability
    low = math.floor(at)
    high = math.ceil(at)
    return values[low] + (at - low) * (values[high] - values[low])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    summary = read_json(args.build / 'public/summary.json')
    neighbourhoods = read_json(args.build / 'public/neighbourhoods.geojson')['features']
    rows = [f['properties'] for f in neighbourhoods]
    grid = read_json(args.build / 'public/grid.geojson')['features']
    hut = read_json(args.build / 'public/hut.geojson')['features']
    quality = read_json(args.build / 'audit/quality.json')
    check('r_build_checks', all(x['passed'] for x in quality['checks']), len(quality['checks']))
    check('73_string_barri_ids', {x['id'] for x in rows} == {f'{i:02d}' for i in range(1, 74)})
    check('point_and_grid_ids_are_strings', all(isinstance(f['properties']['id'], str) for f in hut + grid))
    check('grid_has_523_pure_polygon_features', len(grid) == 523 and all(f['geometry']['type'] in {'Polygon', 'MultiPolygon'} for f in grid))
    check('two_selected_case_objects', [x['id'] for x in summary['cases']['selected']] == ['10', '40'])
    check('case_flags_match_selected', sorted(x['id'] for x in rows if x['caseFlag']) == ['10', '40'])
    check('hut_geojson_reconciles', len(hut) == sum(x['hutCount'] for x in rows) == summary['totals']['hutIncluded'])
    for dimension, field, class_field in [('level', 'rent2025', 'overlapClass'), ('change', 'rentChange', 'changeClass')]:
        sample = [x for x in rows if x['comparable'] and x['contracts2025'] >= 30 and x[field] is not None
                  and (dimension == 'level' or x['contracts2022'] >= 30)]
        tx = quantile7([x['hutIntensity'] for x in sample], .75)
        ty = quantile7([x[field] for x in sample], .75)
        expected = {}
        for x in sample:
            t, p = x['hutIntensity'] >= tx, x[field] >= ty
            expected[x['id']] = 'both' if t and p else 'tourism' if t else 'rent' if p else 'neither'
        check(dimension + '_independent_classification', all(x[class_field] == expected.get(x['id'], 'unavailable') for x in rows))
        s = summary['overlap'][dimension]
        check(dimension + '_independent_overlap', len(sample) == s['sampleN'] and
              sum(x == 'both' for x in expected.values()) == s['intersection'] and
              sum(x != 'neither' for x in expected.values()) == s['union'])
        check(dimension + '_double_denominator', s['cityIncludedHutDenominator'] == sum(x['hutCount'] for x in rows)
              and s['commonSampleHutDenominator'] == sum(x['hutCount'] for x in sample))
    with (args.build / 'audit/platform_panel.csv').open(newline='') as f:
        panel = list(csv.DictReader(f))
    for k in range(4):
        account = Counter(x['hostId'] for x in panel if x['snapshotIndex'] == str(k) and x['roomType'] == 'Entire home/apt' and x['hostId'])
        observed = next(x for x in summary['charts']['hostStructure'] if x['snapshotIndex'] == k)
        check(f'host_{k}_independent_counts', observed['entireListings'] == sum(account.values()) and all(
            observed[f'managedBy{n}Plus'] == sum(v for v in account.values() if v >= n) for n in (2, 5, 10)))
        spatial = next(x for x in summary['dataQuality']['platformSpatial'] if x['snapshotIndex'] == k)
        check(f'grid_{k}_totals', sum(x['properties'][f'n{k}'] for x in grid) == spatial['currentMapped']
              and sum(x['properties'][f'refN{k}'] for x in grid) == spatial['fixedReferenceMapped'])
    for k in range(1, 4):
        check(f'grid_pair_{k}_net_identity', all(x['properties'][f'refN{k}'] - x['properties'][f'refN{k-1}'] ==
              x['properties'][f'new{k}'] - x['properties'][f'lost{k}'] for x in grid))
    deterministic = {'status': 'not_requested'}
    if args.compare:
        a = {p.relative_to(args.build).as_posix(): sha(p) for p in args.build.rglob('*') if p.is_file()}
        b = {p.relative_to(args.compare).as_posix(): sha(p) for p in args.compare.rglob('*') if p.is_file()}
        differences = [p for p in sorted(set(a) | set(b)) if a.get(p) != b.get(p)]
        deterministic = {'status': 'matched' if not differences else 'different', 'artifactsA': len(a),
                         'artifactsB': len(b), 'differences': differences, 'hashes': a}
        check('two_independent_builds_byte_identical', not differences, len(a))
    report = {'interface_and_independent_calculation_checks': checks,
              'passed': sum(x['passed'] for x in checks), 'total': len(checks),
              'deterministic_rebuild': deterministic,
              'semantic_and_geographic_scope': {'status': 'restricted_adoption', 'unconfirmedBarriIds': ['11', '12'],
                  'pendingRegisterRecords': summary['totals']['hutPending'],
                  'statement': 'Structural and deterministic checks do not resolve geographic scope, legality, occupancy, or causal identification.'},
              'pipelineScriptSha256': sha(Path(__file__).parent / 'build.R')}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'total': report['total'], 'rebuild': deterministic['status']}, ensure_ascii=False))
    raise SystemExit(0 if all(x['passed'] for x in checks) else 1)


if __name__ == '__main__':
    main()
