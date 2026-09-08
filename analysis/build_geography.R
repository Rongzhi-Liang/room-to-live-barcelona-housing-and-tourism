#!/usr/bin/env Rscript
# Rebuild the adopted municipal geometry without depending on rental transforms.
suppressPackageStartupMessages({library(sf);library(jsonlite);library(digest)})
args<-commandArgs(trailingOnly=TRUE)
arg<-function(name,default=NULL){k<-match(paste0('--',name),args);if(is.na(k))default else args[k+1L]}
raw_root<-arg('raw-root');manifest_path<-arg('manifest');out<-arg('out');policy_path<-arg('policy')
stopifnot(!is.null(raw_root),!is.null(manifest_path),!is.null(out),!is.null(policy_path))
manifest<-fromJSON(manifest_path)
input_rel<-'raw/geography/cartobcn_extracted/0301100100_UNITATS_ADM_POLIGONS.json'
expected<-manifest$files$sha256[manifest$files$path==input_rel]
input<-file.path(raw_root,sub('^raw/','',input_rel))
stopifnot(length(expected)==1,file.exists(input),digest(file=input,algo='sha256')==expected)
policy<-fromJSON(policy_path)
stopifnot(policy$declared_before_comparison,policy$numeric_area_tolerance_m2==1)
dir.create(out,recursive=TRUE,showWarnings=FALSE)
c<-st_read(input,quiet=TRUE)
stopifnot(st_crs(c)$epsg==25831)
x<-c[c$TIPUS_UA=='BARRI',];x<-x[order(as.integer(x$BARRI)),]
x$id<-sprintf('%02d',as.integer(x$BARRI));x$name<-x$NOM
stopifnot(nrow(x)==73,identical(x$id,sprintf('%02d',1:73)),!anyDuplicated(x$id),all(st_is_valid(x)),!any(st_is_empty(x)))
ai<-c[c$TIPUS_UA=='AREA_I',];city<-c[c$TIPUS_UA=='TERME',]
stopifnot(nrow(ai)==2,all(st_is_valid(ai)),all(st_is_valid(city)))
outside<-sapply(seq_len(nrow(ai)),function(j)sum(as.numeric(st_area(st_difference(st_geometry(ai)[j],st_geometry(x[x$id==ai$BARRI[j],]))))))
stopifnot(all(outside<=policy$numeric_area_tolerance_m2))
un<-st_union(st_geometry(x))
x$barri_id<-x$id;x$geometry_source<-'Ajuntament de Barcelona / CartoBCN product 102';x$geometry_snapshot_date<-'2026-09-06';x$geometry_archive_file_date<-'2025-02-06'
x$statistics_scope_verified<-!x$id%in%c('11','12');x$comparable<-x$statistics_scope_verified
x$aei_geometry_verified<-x$id%in%c('11','12')
x$scope_status<-ifelse(x$comparable,'standard_barri_correspondence_accepted','aei_containment_verified_cross_source_scope_pending')
x$area_km2<-as.numeric(st_area(x))/1e6
export<-st_transform(x[,c('id','barri_id','name','DISTRICTE','statistics_scope_verified','comparable','aei_geometry_verified','scope_status','geometry_source','geometry_snapshot_date','geometry_archive_file_date','area_km2')],4326)
putgeo<-function(z,name)st_write(z,file.path(out,name),delete_dsn=TRUE,quiet=TRUE,layer_options='COORDINATE_PRECISION=8')
putgeo(export,'barcelona_barri_73_wgs84.geojson')
putgeo(st_transform(city[,c('NOM')],4326),'barcelona_city_wgs84.geojson')
putgeo(st_transform(st_sf(id='barcelona_analysis_union',geometry=un),4326),'barcelona_analysis_union_wgs84.geojson')
putgeo(st_transform(ai[,c('BARRI','NOM')],4326),'barcelona_aei_wgs84.geojson')
# The opening map uses the municipality and its ten districts.
context<-c[c$TIPUS_UA%in%c('TERME','DISTRICTE'),]
context<-context[order(context$TIPUS_UA,context$DISTRICTE),]
stopifnot(nrow(context)==11,sum(context$TIPUS_UA=='DISTRICTE')==10,all(st_is_valid(context)))
context$kind<-ifelse(context$TIPUS_UA=='TERME','city','district')
context$id<-ifelse(context$kind=='city','barcelona',context$DISTRICTE)
context$name<-context$NOM
context_out<-arg('context-out',file.path(out,'city-context.geojson'))
st_write(st_transform(context[,c('id','kind','name')],4326),context_out,delete_dsn=TRUE,quiet=TRUE,layer_options='COORDINATE_PRECISION=8')
audit<-list(status='adopted_core_geometry_rebuilt',source_sha256=expected,policy_sha256=digest(file=policy_path,algo='sha256'),
    barri_count=73,comparable_count=71,pending_scope_ids=c('11','12'),aei_outside_parent_m2=outside,
    limits='Geometry containment does not resolve the 11/12 cross-source statistical extraction scope. These two areas remain outside the common comparison sample.',
    R=as.character(getRversion()),sf=as.character(packageVersion('sf')),spatial_libraries=as.list(sf_extSoftVersion()))
write_json(audit,file.path(out,'geography_core_rebuild.json'),pretty=TRUE,auto_unbox=TRUE,digits=15)
cat('Rebuilt four official geometry assets; 73 geometries, 71 comparable, 11/12 scope restrictions preserved.\n')
