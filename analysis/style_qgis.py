#!/usr/bin/env python3
"""Build local QGIS styles/project using the installed QGIS Python runtime."""
import argparse
import json
import os
import gc
from pathlib import Path
import xml.etree.ElementTree as ET

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import (Qgis, QgsApplication, QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
                       QgsReferencedRectangle, QgsFillSymbol, QgsMarkerSymbol, QgsRuleBasedRenderer,
                       QgsMapLayerStyle, QgsExpression, QgsRenderContext, QgsExpressionContext, QgsExpressionContextUtils)
from qgis.PyQt.QtGui import QColor


def build():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    styles = out / 'styles'
    styles.mkdir(exist_ok=True)
    project = QgsProject.instance()
    project.setTitle('Room to Live | Barcelona research inspection')
    project.setFileName(str(out / 'room_to_live_research.qgs'))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setCrs(QgsCoordinateReferenceSystem('EPSG:25831'))
    project.setBackgroundColor(QColor('#F2F0EB'))
    gpkg = out / 'room_to_live_research.gpkg'
    layers = {}
    for name, label in [('neighbourhoods', 'Neighbourhoods | adopted sample and overlap'),
                        ('grid', 'Platform observations | 500 m grid'),
                        ('hut', 'Tourist-home register | included records'),
                        ('qualitative', 'Public evidence | contextual areas')]:
        layer = QgsVectorLayer(str(gpkg) + '|layername=' + name, label, 'ogr')
        if not layer.isValid():
            raise RuntimeError('Invalid QGIS layer: ' + name)
        project.addMapLayer(layer)
        layers[name] = layer

    def fill(color, hatch=False):
        return QgsFillSymbol.createSimple({'color': color, 'outline_color': '#F2F0EB', 'outline_width': '0.13',
                                           'outline_width_unit': 'MM', 'style': 'b_diagonal' if hatch else 'solid'})

    rules_checked = []

    def renderer(spec):
        root = QgsRuleBasedRenderer.Rule(None)
        for expression, label, color, hatch in spec:
            test = QgsExpression(expression)
            if test.hasParserError():
                raise RuntimeError(test.parserErrorString())
            rule = QgsRuleBasedRenderer.Rule(fill(color, hatch))
            rule.setFilterExpression(expression)
            rule.setLabel(label)
            root.appendChild(rule)
            rules_checked.append(expression)
        return QgsRuleBasedRenderer(root)

    def bins(field, bounds, labels, valid_field):
        palette = ['#E4E0D9', '#D4BDB0', '#DDA487', '#D77450', '#C7472E']
        spec = [(f'NOT "{valid_field}"', 'Outside adopted comparison sample', '#BAB8B2', True)]
        for k, label in enumerate(labels):
            parts = [f'"{valid_field}"']
            if bounds[k] is not None:
                parts.append(f'"{field}" >= {bounds[k]}')
            if bounds[k + 1] is not None:
                parts.append(f'"{field}" < {bounds[k + 1]}')
            spec.append((' AND '.join(parts), label, palette[k], False))
        return spec

    def overlap(field):
        return [(f'"{field}" = \'{value}\'', label, color, hatch) for value, label, color, hatch in [
            ('both', 'High HUT and high rent indicator', '#C7472E', False),
            ('tourism', 'High HUT only', '#DDA487', False),
            ('rent', 'High rent indicator only', '#777672', False),
            ('neither', 'Neither high group', '#DFDCD5', False),
            ('unavailable', 'Outside adopted comparison sample', '#BAB8B2', True)]]

    specs = {
        'hut_intensity': bins('hutIntensity', [0, 1, 5, 15, 30, None], ['0–<1', '1–<5', '5–<15', '15–<30', '30+ registrations / 1,000 units'], 'comparable'),
        'rent_level': bins('rent2025', [None, 12, 15, 18, 21, None], ['<12', '12–<15', '15–<18', '18–<21', '21+ EUR/m²/month'], 'mainSampleLevel'),
        'rent_change': bins('rentChange', [None, 0, 10, 20, 30, None], ['<0%', '0–<10%', '10–<20%', '20–<30%', '30%+ (2022–2025)'], 'mainSampleChange'),
        'overlap_level': overlap('overlapClass'),
        'overlap_change': overlap('changeClass')}
    n = layers['neighbourhoods']
    for name, spec in specs.items():
        n.setRenderer(renderer(spec))
        style = QgsMapLayerStyle()
        style.readFromLayer(n)
        n.styleManager().addStyle(name, style)
        result = n.saveNamedStyle(str(styles / (name + '.qml')))
        if not result[1]:
            raise RuntimeError('Style save failed: ' + name)
    n.setRenderer(renderer(specs['overlap_level']))
    n.setDisplayExpression('"id" || \' · \' || "name"')

    layers['hut'].renderer().setSymbol(QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '#C7472E',
        'outline_style': 'no', 'size': '0.7', 'size_unit': 'MM'}))
    layers['grid'].setRenderer(renderer([
        ('"n3" = 0', 'No listing observed in latest snapshot', '#E4E0D9', False),
        ('"n3" > 0 AND "n3" < 20', '1–19 observations', '#D4BDB0', False),
        ('"n3" >= 20 AND "n3" < 100', '20–99 observations', '#DDA487', False),
        ('"n3" >= 100 AND "n3" < 300', '100–299 observations', '#D77450', False),
        ('"n3" >= 300', '300+ observations', '#C7472E', False)]))
    layers['qualitative'].renderer().setSymbol(QgsFillSymbol.createSimple({'style': 'no', 'outline_color': '#C7472E',
        'outline_style': 'dash', 'outline_width': '0.5', 'outline_width_unit': 'MM'}))
    for name in ['hut', 'grid', 'qualitative']:
        result = layers[name].saveNamedStyle(str(styles / (name + '.qml')))
        if not result[1]:
            raise RuntimeError('Style save failed: ' + name)
        project.layerTreeRoot().findLayer(layers[name].id()).setItemVisibilityChecked(False)
    project.layerTreeRoot().findLayer(n.id()).setItemVisibilityChecked(True)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(n.extent(), project.crs()))
    if not project.write():
        raise RuntimeError('QGIS project write failed')

    # Keep the inspection package free of machine-user metadata and absolute source paths.
    project_file = out / 'room_to_live_research.qgs'
    tree = ET.parse(project_file)
    root = tree.getroot()
    for attribute in ['saveUser', 'saveUserFull']:
        root.attrib.pop(attribute, None)
    tree.write(project_file, encoding='UTF-8', xml_declaration=True)
    datasources = [x.text for x in root.findall('.//projectlayers/maplayer/datasource')]
    if len(datasources) != 4 or any(not x.startswith('./room_to_live_research.gpkg|layername=') for x in datasources):
        raise RuntimeError('Project sources are not the four relative GeoPackage layers')

    expected = {'neighbourhoods': 73, 'hut': 10622, 'grid': 523, 'qualitative': 7}
    counts = {name: layer.featureCount() for name, layer in layers.items()}
    if counts != expected:
        raise RuntimeError('QGIS feature count mismatch')
    # Load every QML back into its intended geometry type and evaluate the renderer.
    style_checks = []
    for style_file in sorted(styles.glob('*.qml')):
        target = style_file.stem if style_file.stem in {'hut', 'grid', 'qualitative'} else 'neighbourhoods'
        probe = QgsVectorLayer(str(gpkg) + '|layername=' + target, target, 'ogr')
        result = probe.loadNamedStyle(str(style_file))
        if not result[1] or probe.renderer() is None:
            raise RuntimeError('QML readback failed: ' + style_file.name)
        if target == 'neighbourhoods':
            context = QgsRenderContext()
            probe.renderer().startRender(context, probe.fields())
            rendered = sum(probe.renderer().willRenderFeature(f, context) for f in probe.getFeatures())
            probe.renderer().stopRender(context)
            if rendered != 73:
                raise RuntimeError('Style has unclassified neighbourhoods: ' + style_file.name)
            expression_context = QgsExpressionContext()
            expression_context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(probe))
            counts_by_rule = {rule.label(): 0 for rule in probe.renderer().rootRule().children()}
            for feature in probe.getFeatures():
                expression_context.setFeature(feature)
                matches = []
                for rule in probe.renderer().rootRule().children():
                    expression = QgsExpression(rule.filterExpression())
                    if bool(expression.evaluate(expression_context)):
                        matches.append(rule.label())
                if len(matches) != 1:
                    raise RuntimeError('Neighbourhood must match exactly one display rule: ' + style_file.name)
                counts_by_rule[matches[0]] += 1
        else:
            counts_by_rule = None
        style_checks.append({'file': style_file.name, 'qgis_load_valid': True, 'neighbourhood_rule_counts': counts_by_rule})
    project.clear()
    if not project.read(str(project_file)) or len(project.mapLayers()) != 4 or not all(x.isValid() for x in project.mapLayers().values()):
        raise RuntimeError('QGS project readback failed')
    report = {'status': 'headless_qgis_readback_passed', 'QGIS': Qgis.QGIS_VERSION, 'features': counts,
              'project_sources': datasources, 'styles': style_checks, 'rule_expressions_parsed': len(rules_checked),
              'desktop_ui_acceptance': 'not_performed',
              'limits': 'Provider loads, QML expressions/styles and QGS relative data sources were checked in the installed QGIS runtime. No desktop interaction or visible map acceptance is claimed.'}
    (out / 'qgis_headless_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (out / 'room_to_live_research.qgs~').unlink(missing_ok=True)
    project.clear()
    print(json.dumps({'status': report['status'], 'features': counts, 'styles': len(style_checks)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    app = QgsApplication([], False)
    app.initQgis()
    try:
        build()
    finally:
        QgsProject.instance().clear()
        gc.collect()
        app.exitQgis()
