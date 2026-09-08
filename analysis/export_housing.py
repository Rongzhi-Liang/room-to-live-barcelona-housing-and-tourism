"""Export the frozen housing tables as deterministic Excel workbooks.

Uses only Python's standard library. Source identifiers stay text, while
years and residential-unit counts become numeric cells. No formulas are added.
"""
from pathlib import Path
import argparse
import json
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
SOURCE_URL = 'https://opendata-ajuntament.barcelona.cat/data/en/dataset/est-cadastre-habitatges-superficie'


def export(raw, out):
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for year in (2025, 2026):
        pages = [json.loads(p.read_text()) for p in sorted((raw / 'ckan' / f'housing_{year}').glob('page_*.json'))]
        records = [r for page in pages for r in page['result']['records']]
        columns = [f['id'] for f in pages[0]['result']['fields']]
        assert columns == ['_id', 'Any', 'Codi_districte', 'Nom_districte', 'Codi_barri', 'Nom_barri', 'Seccio_censal', 'Desc_sup', 'Nombre']
        assert len({r['_id'] for r in records}) == len(records) == pages[0]['result']['total']
        assert all(int(r['Any']) == year for r in records)
        units = sum(int(r['Nombre']) for r in records)
        assert units == {2025: 835485, 2026: 836621}[year]
        matrix = [[int(r[k]) if k in ('Any', 'Nombre') else str(r[k]) for k in columns] for r in records]
        last = len(records) + 5

        def cell(ref, value, style=0):
            if isinstance(value, int):
                return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
            return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'

        def row(number, values, styles, height):
            cells = ''.join(cell(f'{chr(65+i)}{number}', v, styles[i]) for i, v in enumerate(values))
            return f'<row r="{number}" ht="{height}" customHeight="1">{cells}</row>'

        sheet_rows = [
            row(1, [f'Barcelona residential units {year} / 巴塞罗那住宅数量 {year}'], [1], 30),
            row(2, [f'Source: Ajuntament de Barcelona, Open Data BCN. {SOURCE_URL}'], [2], 24),
            row(3, ['Nombre = residential units / 住宅数量; Desc_sup = floor-area band (m²) / 面积分组。Excel copy of the published data / 官方数据的 Excel 副本。CC BY 4.0.'], [2], 24),
            row(5, columns, [3] * 9, 26),
        ]
        for number, values in enumerate(matrix, 6):
            sheet_rows.append(row(number, values, [4, 4, 4, 0, 4, 0, 4, 0, 5], 19))
        widths = [11, 10, 17, 25, 14, 56, 18, 20, 14]
        cols = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1))
        sheet = f'''<worksheet xmlns="{NS}" xmlns:r="{REL}">
<dimension ref="A1:I{last}"/><sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A6" sqref="A6"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="19"/><cols>{cols}</cols><sheetData>{''.join(sheet_rows)}</sheetData>
<mergeCells count="3"><mergeCell ref="A1:I1"/><mergeCell ref="A2:I2"/><mergeCell ref="A3:I3"/></mergeCells>
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.25" footer="0.25"/><tableParts count="1"><tablePart r:id="rId1"/></tableParts></worksheet>'''
        styles = f'''<styleSheet xmlns="{NS}">
<fonts count="4"><font><sz val="10"/><color rgb="FF222222"/><name val="Arial"/></font><font><b/><sz val="15"/><color rgb="FF222222"/><name val="Arial"/></font><font><sz val="10"/><color rgb="FF555555"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF303030"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleLight1" defaultPivotStyle="PivotStyleLight16"/></styleSheet>'''
        table_columns = ''.join(f'<tableColumn id="{i}" name="{k}"/>' for i, k in enumerate(columns, 1))
        parts = {
            '[Content_Types].xml': '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>''' + ''.join(f'<Override PartName="/{p}" ContentType="{t}"/>' for p, t in [
                ('xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
                ('xl/worksheets/sheet1.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'),
                ('xl/styles.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'),
                ('xl/tables/table1.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml'),
                ('docProps/core.xml', 'application/vnd.openxmlformats-package.core-properties+xml'),
                ('docProps/app.xml', 'application/vnd.openxmlformats-officedocument.extended-properties+xml')]) + '</Types>',
            '_rels/.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="{REL}/extended-properties" Target="docProps/app.xml"/></Relationships>',
            'xl/workbook.xml': f'<workbook xmlns="{NS}" xmlns:r="{REL}"><bookViews><workbookView/></bookViews><sheets><sheet name="Housing {year}" sheetId="1" r:id="rId1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/></Relationships>',
            'xl/worksheets/sheet1.xml': sheet,
            'xl/worksheets/_rels/sheet1.xml.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/table" Target="../tables/table1.xml"/></Relationships>',
            'xl/styles.xml': styles,
            'xl/tables/table1.xml': f'<table xmlns="{NS}" id="1" name="Housing{year}" displayName="Housing{year}" ref="A5:I{last}" totalsRowShown="0"><autoFilter ref="A5:I{last}"/><tableColumns count="9">{table_columns}</tableColumns><tableStyleInfo name="TableStyleLight1" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>',
            'docProps/core.xml': f'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Barcelona residential units {year}</dc:title><dc:creator>Rongzhi Liang</dc:creator><dc:description>Excel copy of Open Data BCN housing statistics. Source: {SOURCE_URL}</dc:description></cp:coreProperties>',
            'docProps/app.xml': '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Room to Live data exporter</Application></Properties>',
        }
        path = out / f'barcelona_housing_{year}.xlsx'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, text in sorted(parts.items()):
                info = zipfile.ZipInfo(name, (2026, 9, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + text, compresslevel=9)
        # Reopen the saved file and compare every cell with the frozen data.
        with zipfile.ZipFile(path) as z:
            for name in parts:
                ET.fromstring(z.read(name))
            root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            back = []
            for element in root.findall(f'{{{NS}}}sheetData/{{{NS}}}row'):
                if int(element.attrib['r']) < 6:
                    continue
                values = [c.findtext(f'{{{NS}}}is/{{{NS}}}t') if c.attrib.get('t') == 'inlineStr'
                          else int(c.findtext(f'{{{NS}}}v')) for c in element]
                back.append(values)
            assert back == matrix
            assert root.find(f'.//{{{NS}}}pane').attrib['ySplit'] == '5'
        results.append({'year': year, 'rows': len(matrix), 'cells_checked': len(matrix) * 9, 'residential_units': units})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.raw_root, args.out)))
