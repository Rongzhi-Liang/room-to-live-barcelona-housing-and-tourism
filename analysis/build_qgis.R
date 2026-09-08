#!/usr/bin/env Rscript
# Package accepted public research assets for local QGIS inspection.
suppressPackageStartupMessages({library(sf);library(jsonlite);library(digest)})
sf_use_s2(FALSE)
args<-commandArgs(trailingOnly=TRUE)
arg<-function(name,default=NULL){k<-match(paste0('--',name),args);if(is.na(k))default else args[k+1L]}
public_root<-arg('public-root');out<-arg('out')
stopifnot(!is.null(public_root),!is.null(out),dir.exists(public_root))
dir.create(out,recursive=TRUE,showWarnings=FALSE)
layers<-c('neighbourhoods','hut','grid','qualitative');expected<-c(73L,10622L,523L,7L)
data<-list();qa<-list()
for(k in seq_along(layers)) {
  name<-layers[k];file<-file.path(public_root,paste0(name,'.geojson'))
  x<-st_read(file,quiet=TRUE)
  stopifnot(nrow(x)==expected[k],!any(st_is_empty(x)),all(st_is_valid(x)))
  x$id<-as.character(x$id)
  stopifnot(!anyNA(x$id),!anyDuplicated(x$id))
  data[[name]]<-st_transform(x,25831)
  stopifnot(all(st_is_valid(data[[name]])),!any(st_is_empty(data[[name]])))
  qa[[name]]<-list(input_file=basename(file),input_sha256=digest(file=file,algo='sha256'),features=nrow(x),valid_metric_geometry=TRUE)
}
n<-data$neighbourhoods
n$mainSampleLevel<-n$comparable & n$validRent2025 & n$overlapClass!='unavailable'
n$mainSampleChange<-n$comparable & n$validRentChange & n$changeClass!='unavailable'
n$mainSample<-n$mainSampleLevel & n$mainSampleChange
stopifnot(sum(n$mainSampleLevel)==66,sum(n$mainSampleChange)==66,sum(n$mainSample)==66,
          identical(sort(n$id[n$caseFlag]),c('10','40')))
data$neighbourhoods<-n
gpkg<-file.path(out,'room_to_live_research.gpkg')
for(k in seq_along(layers)) {
  name<-layers[k]
  st_write(data[[name]],gpkg,layer=name,driver='GPKG',delete_dsn=k==1,delete_layer=TRUE,quiet=TRUE)
  back<-st_read(gpkg,layer=name,quiet=TRUE)
  stopifnot(nrow(back)==expected[k],identical(as.character(back$id),data[[name]]$id),all(st_is_valid(back)),!any(st_is_empty(back)))
  a<-st_drop_geometry(data[[name]]);b<-st_drop_geometry(back)
  stopifnot(setequal(names(a),names(b)))
  for(field in names(a)) {
    if(is.numeric(a[[field]])||is.logical(a[[field]]))stopifnot(isTRUE(all.equal(as.numeric(a[[field]]),as.numeric(b[[field]]),tolerance=0)))
    else stopifnot(identical(as.character(a[[field]]),as.character(b[[field]])))
  }
  qa[[name]]$readback_fields_and_values_equal<-TRUE
}
stopifnot(setequal(st_layers(gpkg)$name,layers))
script_arg<-grep('^--file=',commandArgs(),value=TRUE)[1]
script_dir<-dirname(normalizePath(gsub('~+~',' ',sub('^--file=','',script_arg),fixed=TRUE)))
default_python<-if(file.exists('/Applications/QGIS.app/Contents/MacOS/python'))'/Applications/QGIS.app/Contents/MacOS/python'else Sys.getenv('QGIS_PYTHON','python3')
qgis_python<-arg('qgis-python',default_python)
code<-system2(qgis_python,c(shQuote(file.path(script_dir,'style_qgis.py')),'--out',shQuote(normalizePath(out))),env='QT_QPA_PLATFORM=offscreen')
if(code!=0)stop('GeoPackage was built; QGIS project/style generation failed. See the command output and inspect the existing local QGIS Python runtime.')
report<-list(status='geopackage_and_qgis_assets_built_headlessly',layers=qa,metric_crs='EPSG:25831',main_sample=list(level=66,change=66,intersection=66),
  geography_restrictions=c('11','12'),case_ids=c('10','40'),R=as.character(getRversion()),sf=as.character(packageVersion('sf')),
  verification='All four GeoPackage layers were read back with exact field/ID/indicator values and valid nonempty geometry. QGIS project/style checks are headless; desktop UI acceptance is separate.',
  archive_note='GeoPackage metadata timestamps and QGIS XML identifiers can differ across exports; feature/attribute equivalence is the research check, not an asserted binary identity for this inspection package.')
write_json(report,file.path(out,'qgis_build_report.json'),pretty=TRUE,auto_unbox=TRUE,digits=15)
cat('QGIS package built: 73 / 10622 / 523 / 7 features; main samples 66 / 66. Desktop UI acceptance remains separate.\n')
