#!/usr/bin/env python3
"""Rebuild the Barcelona research, QGIS project, upload layers and bilingual website."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='/', help='Website path, for example /room-to-live/ for GitHub Pages.')
    args = parser.parse_args()
    if not args.base.startswith('/') or not args.base.endswith('/'):
        parser.error('--base must start and end with /.')
    os.chdir(ROOT)
    env = os.environ.copy()
    node = env.get('NODE_BINARY') or shutil.which('node')
    rscript = env.get('RSCRIPT') or shutil.which('Rscript')
    pnpm = env.get('PNPM') or shutil.which('pnpm')
    qgis = env.get('QGIS_PYTHON')
    if not qgis and Path('/Applications/QGIS.app/Contents/MacOS/python').is_file():
        qgis = '/Applications/QGIS.app/Contents/MacOS/python'
    if not all((node, rscript, pnpm, qgis)):
        raise SystemExit('Missing runtime. See README: Node.js, pnpm, Rscript and QGIS Python are required. Executable paths can be supplied with NODE_BINARY, PNPM, RSCRIPT and QGIS_PYTHON.')
    env['PATH'] = str(Path(node).parent) + os.pathsep + env.get('PATH', '')
    env['TZ'] = 'UTC'
    env['QT_QPA_PLATFORM'] = 'offscreen'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if (ROOT / '.r-library').is_dir():
        env['R_LIBS_USER'] = str(ROOT / '.r-library')

    def run(command, cwd=ROOT):
        subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)

    def py(script, *arguments):
        run([sys.executable, ROOT / 'analysis' / script, *arguments])

    print('1/8  Check software and frozen inputs', flush=True)
    run([node, '--version'])
    run([pnpm, '--version'])
    run([rscript, '-e', '''lock<-jsonlite::fromJSON('renv.lock',simplifyVector=FALSE);bad<-vapply(lock$Packages,function(p)!requireNamespace(p$Package,quietly=TRUE)||packageVersion(p$Package)!=package_version(p$Version),logical(1));if(any(bad))stop(paste('Restore the R package versions in renv.lock:',paste(names(bad)[bad],collapse=', ')));cat('R ',as.character(getRversion()),'; package versions match renv.lock\\n',sep='');print(sf::sf_extSoftVersion())'''])
    manifest = read(ROOT / 'data/inputs.json')
    archive = ROOT / 'data' / manifest['archive']
    if sha(archive) != manifest['archive_sha256']:
        raise SystemExit('The frozen input archive does not match data/inputs.json.')
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    for folder in ('inputs', 'research', 'repeat', 'geography', 'editorial', 'qgis', 'mapbox'):
        path = build / folder
        if path.is_symlink():
            raise SystemExit('Refusing to replace a symlink: ' + str(path))
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()
    raw = build / 'inputs'
    expected = {f['path'].removeprefix('raw/'): f for f in manifest['files']}
    with zipfile.ZipFile(archive) as z:
        if set(z.namelist()) != set(expected) or len(z.namelist()) != len(expected):
            raise SystemExit('Input archive membership differs from the manifest.')
        for name, entry in expected.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise SystemExit('Unsafe archive path: ' + name)
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise SystemExit('Input checksum mismatch: ' + name)
            path = raw / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    print('2/8  Rebuild official geography', flush=True)
    run([rscript, 'analysis/build_geography.R', '--raw-root', raw,
         '--manifest', 'data/inputs.json', '--policy', 'config/geography_comparison_policy.json',
         '--out', build / 'geography', '--context-out', build / 'city-context.geojson'])
    geography = build / 'geography/barcelona_barri_73_wgs84.geojson'

    print('3/8  Rebuild the research twice and check every output', flush=True)
    for name in ('research', 'repeat'):
        run([rscript, 'analysis/build.R', '--raw-root', raw, '--out', build / name,
             '--geometry', geography, '--config', 'config/study.json', '--manifest', 'data/inputs.json',
             '--case-evidence', 'config/case_evidence.json', '--case-a', '10', '--case-b', '40'])
    py('validate.py', '--build', build / 'research', '--compare', build / 'repeat', '--report', build / 'validation.json')

    print('4/8  Rebuild the bilingual story and place evidence', flush=True)
    areas = {f['properties']['id']: f['geometry'] for f in read(geography)['features']}
    city = read(build / 'geography/barcelona_city_wgs84.geojson')['features'][0]['geometry']
    place_config = read(ROOT / 'config/places.json')
    collection = {'type': 'FeatureCollection', 'name': place_config['name'], 'features': [
        {'type': 'Feature', 'id': p['id'], 'properties': p['properties'],
         'geometry': areas[p['properties']['barri_id']] if p['properties']['barri_id'] else city}
        for p in place_config['places']]}
    write(build / 'qualitative.geojson', collection)
    reference = read(ROOT / 'data/reference.json')
    for name, value in reference['files'].items():
        if sha(build / name) != value:
            raise SystemExit('Reference mismatch: ' + name + '. Check software versions and frozen inputs.')
    for name, rule in reference['json_values'].items():
        obj = read(build / name)
        for pointer in rule['omit']:
            keys = pointer.lstrip('/').split('/')
            parent = obj
            for key in keys[:-1]:
                parent = parent.get(key, {})
            parent.pop(keys[-1], None)
        canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        if hashlib.sha256(canonical).hexdigest() != rule['sha256']:
            raise SystemExit('Reference values differ: ' + name)
    py('build_editorial.py', '--repo', ROOT, '--public-root', build / 'research/public',
       '--template', 'config/editorial_template.json', '--sources', 'config/sources.json',
       '--places', build / 'qualitative.geojson', '--metadata', raw / 'metadata/habitatges-us-turistic.json',
       '--out', build / 'editorial')
    public = ROOT / 'site/public/data'
    if public.is_symlink():
        raise SystemExit('Generated public data directory must not be a symlink.')
    if public.exists():
        shutil.rmtree(public)
    public.mkdir(parents=True)
    for name in ('summary.json', 'neighbourhoods.geojson', 'hut.geojson', 'grid.geojson'):
        shutil.copyfile(build / 'research/public' / name, public / name)
    for name in ('qualitative.geojson', 'city-context.geojson'):
        shutil.copyfile(build / name, public / name)
    shutil.copyfile(build / 'editorial/editorial.resolved.json', public / 'editorial.json')
    shutil.copyfile(ROOT / 'config/sources.json', public / 'sources.json')

    print('5/8  Export the two housing workbooks and check every cell', flush=True)
    from analysis.export_housing import export
    workbooks = export(raw, public / 'downloads')
    write(build / 'workbooks.json', workbooks)

    print('6/8  Rebuild the QGIS project and four upload layers', flush=True)
    run([rscript, 'analysis/build_qgis.R', '--public-root', public, '--out', build / 'qgis', '--qgis-python', qgis])
    for name in ('neighbourhoods', 'hut', 'grid', 'qualitative'):
        shutil.copyfile(public / (name + '.geojson'), build / 'mapbox' / (name + '.geojson'))
    py('assemble_style.py', '--base', 'site/public/mapbox/base.style.json',
       '--registry', 'site/public/mapbox/registry.json', '--data-dir', public,
       '--out', build / 'mapbox/room-to-live.style.json')

    print('7/8  Install locked web dependencies and compile the website', flush=True)
    run([pnpm, 'install', '--frozen-lockfile'], ROOT / 'site')
    run([pnpm, 'run', 'build', '--base=' + args.base], ROOT / 'site')

    print('8/8  Write the reproduction result', flush=True)
    results = {'frozen_inputs': len(expected), 'reference_files': len(reference['files']),
               'reference_json_objects': len(reference['json_values']),
               'independent_validation': read(build / 'validation.json')['passed'],
               'housing_cells_checked': sum(w['cells_checked'] for w in workbooks),
               'public_assets': {p.relative_to(public).as_posix(): sha(p) for p in sorted(public.rglob('*')) if p.is_file()},
               'website_base': args.base, 'website_output': 'site/dist', 'qgis_output': 'build/qgis/room_to_live_research.qgs'}
    write(build / 'reproduction.json', results)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
