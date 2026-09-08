"""Assemble an offline Mapbox v8 style from a verified four-tileset registry.

No network, account or upload operations. Input identifiers are used verbatim;
remote existence and real source-layer names must be checked during upload QA.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import tempfile

KEYS = ('neighbourhoods', 'hut', 'grid', 'places')
SOURCE_IDS = {key: 'rtl-' + key for key in KEYS}
LAYER_IDS = ('rtl-t01-hut-per1000-2026', 'rtl-t01-boundaries',
             'rtl-t03-entire-share-june2026', 'rtl-t02-hut-register-points',
             'rtl-t04-evidence-area')


def read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registry_entries(registry):
    if not isinstance(registry, dict):
        raise ValueError('Registry must be an object keyed by neighbourhoods/hut/grid/places.')
    result = {}
    problems = []
    for key in KEYS:
        entry = registry.get(key)
        if not isinstance(entry, dict):
            problems.append(key + ': missing entry')
            continue
        tileset = entry.get('tilesetId')
        layer = entry.get('sourceLayer')
        if not isinstance(tileset, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', tileset):
            problems.append(key + ': tilesetId must be the exact account.tileset identifier')
        if not isinstance(layer, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', layer):
            problems.append(key + ': sourceLayer must be the exact uploaded vector layer name')
        for value in (tileset, layer):
            if isinstance(value, str) and re.search(r'\b(?:TODO|TBD|PLACEHOLDER|REPLACE_ME|YOUR_ACCOUNT|YOUR_TILESET)\b', value, re.I):
                problems.append(key + ': unresolved placeholder is not accepted')
        result[key] = entry
    if not problems and len({entry['tilesetId'] for entry in result.values()}) != 4:
        problems.append('Four independent tilesetId values are required; a shared tileset is not accepted.')
    if problems:
        raise ValueError('Incomplete or invalid registry; no style written. ' + '; '.join(problems))
    return result


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def local_contract(data_dir, evidence_barri):
    files = {key: data_dir/name for key, name in zip(KEYS, (
        'neighbourhoods.geojson', 'hut.geojson', 'grid.geojson', 'qualitative.geojson'))}
    collections = {key: read_json(path) for key, path in files.items()}
    for key, expected in zip(KEYS, (73, 10622, 523, 7)):
        collection = collections[key]
        if collection.get('type') != 'FeatureCollection' or len(collection.get('features', [])) != expected:
            raise ValueError(f'{key}: local field contract expects {expected} features.')
    neighbourhoods = [feature['properties'] for feature in collections['neighbourhoods']['features']]
    by_id = {p.get('id'): p for p in neighbourhoods}
    if set(by_id) != {f'{i:02d}' for i in range(1, 74)}:
        raise ValueError('T01 must retain exact two-digit IDs 01 through 73.')
    if any(not isinstance(p.get('comparable'), bool) for p in neighbourhoods):
        raise ValueError('T01 comparable must remain a boolean in the upload.')
    if any(by_id[code]['comparable'] is not False for code in ('11', '12')):
        raise ValueError('The two unresolved statistical scopes must remain masked.')
    values = [p.get('hutIntensity') for p in neighbourhoods if p['comparable']]
    if not values or not all(is_number(v) and v >= 0 for v in values) or max(values) <= 0:
        raise ValueError('T01 needs finite, nonnegative comparable hutIntensity values.')
    for feature in collections['hut']['features']:
        if feature['geometry']['type'] != 'Point' or not feature['properties'].get('id'):
            raise ValueError('T02 must contain identified registration points.')
    for feature in collections['grid']['features']:
        p = feature['properties']
        if feature['geometry']['type'] not in ('Polygon', 'MultiPolygon'):
            raise ValueError('T03 must have pure polygon geometry.')
        share = p.get('share3')
        if 'share3' not in p or 'n3' not in p or (share is not None and not (is_number(share) and 0 <= share <= 100)):
            raise ValueError('T03 requires share3 in 0–100 or null, plus n3.')
        if p['n3'] == 0 and share is not None:
            raise ValueError('T03 empty-cell shares must remain null, not zero.')
    areas = {f['properties'].get('barri_id') for f in collections['places']['features']}
    if evidence_barri not in areas:
        raise ValueError('Requested evidence barri has no T04 record; no invented location filter written.')
    return min(values), max(values), {key: fingerprint(path) for key, path in files.items()}


def evidence_layers(entries, minimum, maximum, evidence_barri):
    def ref(key):
        return {'source': SOURCE_IDS[key], 'source-layer': entries[key]['sourceLayer']}
    return [
        {'id': LAYER_IDS[0], 'type': 'fill', **ref('neighbourhoods'),
         'layout': {'visibility': 'visible'},
         'paint': {'fill-color': ['case', ['all', ['==', ['get', 'comparable'], True],
                     ['==', ['typeof', ['get', 'hutIntensity']], 'number']],
                     ['interpolate', ['linear'], ['get', 'hutIntensity'], minimum, '#79746f', maximum, '#dc955e'], '#222222'],
                   'fill-opacity': 0.82}},
        {'id': LAYER_IDS[1], 'type': 'line', **ref('neighbourhoods'),
         'paint': {'line-color': '#b7b7b7', 'line-width': 0.55, 'line-opacity': 0.5}},
        {'id': LAYER_IDS[2], 'type': 'fill', **ref('grid'),
         'layout': {'visibility': 'none'},
         'paint': {'fill-color': ['case', ['all', ['>', ['coalesce', ['get', 'n3'], 0], 0],
                     ['==', ['typeof', ['get', 'share3']], 'number']],
                     ['interpolate', ['linear'], ['get', 'share3'], 0, '#777777', 100, '#d77943'], '#222222'],
                   'fill-opacity': 1, 'fill-outline-color': '#525252'}},
        {'id': LAYER_IDS[3], 'type': 'circle', **ref('hut'), 'minzoom': 12,
         'filter': ['has', 'id'], 'layout': {'visibility': 'visible'},
         'paint': {'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 1.4, 15, 3, 18, 4.5],
                   'circle-color': '#efb894', 'circle-opacity': 0.76,
                   'circle-stroke-color': '#242424', 'circle-stroke-width': 0.25}},
        {'id': LAYER_IDS[4], 'type': 'line', **ref('places'),
         'filter': ['==', ['get', 'barri_id'], evidence_barri], 'layout': {'visibility': 'none'},
         'paint': {'line-color': '#e5624d', 'line-width': 2.2, 'line-dasharray': [3, 2], 'line-opacity': 1}}
    ]


def assemble(base, entries, minimum, maximum, evidence_barri):
    if not isinstance(base, dict) or base.get('version') != 8:
        raise ValueError('Base style must use Mapbox style specification version 8.')
    if not isinstance(base.get('sources'), dict) or not isinstance(base.get('layers'), list):
        raise ValueError('Base style needs sources and layers.')
    output = copy.deepcopy(base)
    # Only style/editor metadata is removed. Sources, URLs, attribution, glyphs,
    # sprites, map settings and original paint/layout/filter rules are retained.
    output.pop('metadata', None)
    for source in output['sources'].values():
        source.pop('metadata', None)
    for layer in output['layers']:
        layer.pop('metadata', None)
    if set(SOURCE_IDS.values()) & set(output['sources']):
        raise ValueError('Base already contains an rtl evidence source; use the original base to avoid duplication.')
    if set(LAYER_IDS) & {layer.get('id') for layer in output['layers']}:
        raise ValueError('Base already contains an rtl evidence layer.')
    attribution = {
        'neighbourhoods': 'Ajuntament de Barcelona · CartoBCN / Open Data BCN; Generalitat de Catalunya · INCASÒL',
        'hut': 'Ajuntament de Barcelona · Open Data BCN tourist-home register',
        'grid': 'Inside Airbnb · June–July 2026 observations; Ajuntament de Barcelona · CartoBCN',
        'places': 'Public evidence sources linked in the project source catalogue; Ajuntament de Barcelona · CartoBCN'
    }
    for key in KEYS:
        output['sources'][SOURCE_IDS[key]] = {
            'type': 'vector', 'url': 'mapbox://' + entries[key]['tilesetId'],
            'attribution': entries[key].get('attribution') or attribution[key]}
    insert_at = next((i for i, layer in enumerate(output['layers']) if layer.get('type') == 'symbol'), len(output['layers']))
    output['layers'][insert_at:insert_at] = evidence_layers(entries, minimum, maximum, evidence_barri)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, help='Defaults to the sibling public/data directory of the base style.')
    parser.add_argument('--evidence-barri', default='23', help='Existing T04 two-digit barri_id; default 23 (Sarrià). Layer stays hidden.')
    args = parser.parse_args()
    try:
        entries = registry_entries(read_json(args.registry))
        data_dir = args.data_dir or args.base.parent.parent/'data'
        if not re.fullmatch(r'0[1-9]|[1-6][0-9]|7[0-3]', args.evidence_barri):
            raise ValueError('Evidence barri must be a two-digit code 01–73.')
        input_paths = [args.base.resolve(), args.registry.resolve()] + [p.resolve() for p in data_dir.glob('*.geojson')]
        if args.out.resolve() in input_paths:
            raise ValueError('Output must not overwrite an input.')
        minimum, maximum, hashes = local_contract(data_dir, args.evidence_barri)
        output = assemble(read_json(args.base), entries, minimum, maximum, args.evidence_barri)
        # Everything is checked before any output is created; replacement is atomic.
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=args.out.parent, prefix='.style-', suffix='.tmp', delete=False) as stream:
            temp_name = stream.name
            json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temp_name, args.out)
        print(json.dumps({'written': args.out.name, 'version': 8,
                          'independent_evidence_vector_sources': 4,
                          'hut_intensity_scale': {'min': minimum, 'max': maximum, 'unit': '2026 registrations per 1000 cadastral residential units'},
                          'grid_share': 'Entire-home listing share, 0–100%; null cells remain unavailable; actual collection June–July 2026.',
                          'evidence_barri': args.evidence_barri,
                          'base_sha256': fingerprint(args.base), 'registry_sha256': fingerprint(args.registry),
                          'local_field_contract_sha256': hashes, 'style_sha256': fingerprint(args.out),
                          'remote_verification': 'Not attempted; actual uploaded IDs and source-layer fields require account-side verification.'}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Style assembly failed: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
