#!/usr/bin/env Rscript
# Rebuild the Barcelona housing evidence from frozen public source files.
suppressPackageStartupMessages({
  library(sf); library(dplyr); library(tidyr); library(readr)
  library(readxl); library(jsonlite); library(digest)
})
options(stringsAsFactors = FALSE, scipen = 999, dplyr.summarise.inform = FALSE)
Sys.setenv(TZ = "UTC")
set.seed(5118)
sf_use_s2(FALSE)

args <- commandArgs(trailingOnly = TRUE)
arg <- function(name, default = NULL) {
  k <- match(paste0("--", name), args)
  if (is.na(k)) default else args[k + 1L]
}
raw_root <- arg("raw-root", "build/inputs")
out <- arg("out", "build/research")
geometry_path <- arg("geometry")
config_path <- arg("config")
stopifnot(dir.exists(raw_root))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
for (d in c("public", "tables", "audit")) dir.create(file.path(out,d), showWarnings = FALSE)
cfg <- if (!is.null(config_path)) fromJSON(config_path, simplifyVector = FALSE) else list()
dates <- c("2025-09-14","2025-12-14","2026-03-21","2026-06-24")
id2 <- function(x) { y <- suppressWarnings(as.integer(x)); ifelse(!is.na(y) & y >= 1 & y <= 73, sprintf("%02d",y), NA_character_) }
num <- function(x) suppressWarnings(as.numeric(x))
name_key <- function(x) gsub("[^[:alnum:]]", "", tolower(iconv(x, to="ASCII//TRANSLIT")))
jwrite <- function(x,path) write_json(x, file.path(out,path), pretty=TRUE, auto_unbox=TRUE, na="null", null="null", digits=15)
cwrite <- function(x,path) write_csv(st_drop_geometry(x), file.path(out,path), na="", quote="needed")
checks <- list()
ck <- function(name, ok, detail=NULL, blocking=TRUE) {
  checks[[length(checks)+1L]] <<- list(name=name, passed=isTRUE(ok), detail=detail, blocking=blocking)
  if (!isTRUE(ok) && blocking) stop(paste("Check failed:",name))
}
hash_file <- function(p) digest(file=p,algo="sha256")
input_files <- sort(list.files(raw_root,recursive=TRUE,full.names=TRUE))
input_hashes <- tibble(path=substring(input_files,nchar(raw_root)+2L),sha256=vapply(input_files,hash_file,character(1)))
source_manifest <- arg("manifest",file.path(dirname(raw_root),"source_manifest.json"))
ck("source_manifest_present",file.exists(source_manifest))
if (file.exists(source_manifest)) {
  manifest <- fromJSON(source_manifest)
  expected <- manifest$files %>% mutate(path=sub("^raw/","",path)) %>% select(path,expected=sha256)
  verify <- left_join(expected,input_hashes,by="path")
  ck("frozen_raw_hashes",all(verify$expected==verify$sha256 & !is.na(verify$sha256)),nrow(verify))
}
cwrite(input_hashes,"audit/input_hashes.csv")
settings <- list(rentYear=2025,baseYear=2022,housingYears=c(2025,2026),contractThreshold=30,
                 highShare=0.25,quantileType=7,tieRule="greater than or equal to threshold",
                 sensitivityShares=c(.20,.25,.33),sensitivityContracts=c(15,30,50),sensitivityBases=c(2019,2022,2023),
                 snapshots=dates,crs=25831,gridMetres=500,caseRentGapSD=.5,
                 sourceBarriRule="Valid official registry code retained; unique spatial match recovers missing codes; conflicts flagged",
                 hutRule="Distinct normalized HUTB identifiers with attributable neighbourhood; missing/nonstandard identifiers pending",
                 aeiRule="11/12 excluded from common-sample comparison unless geography explicitly verifies statistical scope")
if(length(cfg)) {
  ck("config_matches_adopted_periods",cfg$years$rent_level==2025 && cfg$years$rent_base==2022 && cfg$years$hut==2026)
  ck("config_matches_thresholds",cfg$price_contract_minimum==30 && cfg$contract_activity_minimum==0 && cfg$high_share==.25 && cfg$quantile_type==7)
  ck("config_matches_snapshots",identical(unlist(cfg$snapshots,use.names=FALSE),dates))
  ck("config_matches_sensitivity",identical(as.numeric(unlist(cfg$contract_thresholds)),c(15,30,50)) && identical(as.numeric(unlist(cfg$high_share_sensitivity)),c(.20,.25,.33)))
  ck("config_matches_grid",cfg$grid$crs==25831 && cfg$grid$size_m==500 && cfg$grid$alternative_size_m==1000 && identical(as.numeric(unlist(cfg$grid$origin_m)),c(0,0)))
  ck("config_matches_case_and_ties",cfg$case_selection$max_distance_sd==.5 && cfg$threshold_ties=="include_equal" && cfg$quantiles_on=="pairwise_common_valid_sample" && cfg$seed==5118)
  settings$configHash <- hash_file(config_path)
}
jwrite(settings,"audit/adopted_settings.json")
if (length(cfg)) jwrite(cfg,"audit/input_study_config.json")

read_ckan <- function(name) {
  paths <- sort(list.files(file.path(raw_root,"ckan",name),pattern="^page_[0-9]+[.]json$",full.names=TRUE))
  rows <- list(); offset <- 0L; total <- NULL
  for (p in paths) {
    d <- fromJSON(p)
    ck(paste0(name,":success:",basename(p)),d$success)
    r <- d$result
    ck(paste0(name,":offset:",basename(p)),r$offset==offset)
    if (is.null(total)) total <- r$total
    ck(paste0(name,":same_total:",basename(p)),r$total==total)
    rows[[length(rows)+1L]] <- as_tibble(r$records)
    offset <- offset+nrow(r$records)
  }
  x <- bind_rows(rows)
  ck(paste0(name,":complete_unique_rows"),nrow(x)==total && n_distinct(x$`_id`)==total)
  x %>% arrange(`_id`)
}

message("Housing and rental tables")
housing <- bind_rows(lapply(c(2025,2026),function(y) {
  x <- read_ckan(paste0("housing_",y)) %>% mutate(barriId=id2(Codi_barri),year=as.integer(Any),count=num(Nombre))
  ck(paste0("housing",y,":code_year_count"),all(!is.na(x$barriId))&&all(x$year==y)&&all(is.finite(x$count)&x$count>=0&x$count==floor(x$count)))
  ck(paste0("housing",y,":unique_area_key"),!anyDuplicated(x[c("Codi_districte","Seccio_censal","Codi_barri","Desc_sup")]))
  expected_groups <- c("Fins a 30 m2","31- 60 m2","61- 90 m2","91- 120 m2","121- 150 m2","151- 210 m2","211- 250 m2","Més de 250 m2")
  ck(paste0("housing",y,":mutually_exclusive_area_labels"),setequal(unique(x$Desc_sup),expected_groups),sort(unique(x$Desc_sup)))
  # The published integer-square-metre bands cover the dwelling counts; no total row is mixed in.
  cwrite(x %>% select(year,barriId,Codi_districte,Seccio_censal,Desc_sup,count),paste0("tables/housing_groups_",y,".csv"))
  z <- x %>% group_by(year,barriId) %>% summarise(name=first(Nom_barri),housing=sum(count),.groups="drop")
  ck(paste0("housing",y,":73_codes"),setequal(z$barriId,sprintf("%02d",1:73)))
  z
}))
cwrite(housing,"tables/housing.csv")
names <- housing %>% filter(year==2026) %>% select(id=barriId,name)
ck("normalized_names_unique",!anyDuplicated(name_key(names$name)))
name_map <- setNames(names$id,name_key(names$name))

read_rent <- function(file, metric) {
  p <- file.path(raw_root,"incasol",file)
  dat <- read_excel(p,col_names=FALSE,col_types="text",.name_repair="minimal")
  h <- which(dat[[1]]=="Codi")[1]
  years <- num(unlist(dat[h,],use.names=FALSE)); cols <- which(!is.na(years)&years>=2000&years<=2100)
  mode <- "city"; result <- list(); notes <- character()
  for (i in seq_len(nrow(dat))) {
    a <- dat[[1]][i]; b <- trimws(dat[[2]][i])
    if (!is.na(a)&&is.na(num(a))&&i!=h) notes <- c(notes,a)
    if (is.na(b)) next
    if (startsWith(b,"Districtes")) {mode<-"district";next}
    if (startsWith(b,"Barris")) {mode<-"neighbourhood";next}
    if (b=="Barcelona") {g<-"city";id<-"00"}
    else if (!is.na(num(a))) {g<-mode;id<-sprintf("%02d",as.integer(a))}
    else next
    value <- unlist(dat[i,cols],use.names=FALSE)
    result[[length(result)+1L]] <- tibble(metric=metric,geography=g,id=id,name=b,year=as.integer(years[cols]),
                 value=num(value),rawValue=value,valueStatus=ifelse(is.na(value),"blank",ifelse(is.na(num(value)),"unpublished_marker","numeric")),sourceRow=i)
  }
  x <- bind_rows(result) %>% filter(year>=2019,year<=2025) %>% arrange(geography,id,year)
  ck(paste0(metric,":unique_area_year"),!anyDuplicated(x[c("geography","id","year")]))
  ck(paste0(metric,":73_neighbourhoods"),setequal(x$id[x$geography=="neighbourhood"],sprintf("%02d",1:73)))
  jwrite(list(file=file,notes=notes),paste0("audit/",metric,"_source_notes.json"))
  x
}
rent <- bind_rows(read_rent("anual_bcn_lloguer.xlsx","rentMonth"),read_rent("anual_bcn_lloguer_m2.xlsx","rentM2"),read_rent("anual_bcn_contractes.xlsx","contracts"))
cwrite(rent,"tables/rent_long.csv")
rent_wide <- rent %>% select(geography,id,name,year,metric,value) %>% pivot_wider(names_from=metric,values_from=value)
coverage <- rent_wide %>% filter(geography=="neighbourhood") %>% group_by(year) %>% summarise(geolocatedContracts=sum(contracts,na.rm=TRUE),.groups="drop") %>%
  left_join(rent_wide %>% filter(geography=="city") %>% select(year,cityContracts=contracts),by="year") %>%
  mutate(notAssignedToNeighbourhood=cityContracts-geolocatedContracts,geolocatedShare=100*geolocatedContracts/cityContracts)
ck("contract_coverage_nonnegative",all(coverage$notAssignedToNeighbourhood>=0))
cwrite(coverage,"tables/contract_coverage.csv")
rent_names <- rent_wide %>% filter(geography=="neighbourhood",year==2025) %>% select(id,rentName=name) %>% left_join(names,by="id") %>% mutate(nameMatches=name_key(rentName)==name_key(name))
cwrite(rent_names,"audit/rent_name_crosswalk.csv")

message("registry records")
hut_raw <- read_ckan("hut_current")
hut <- hut_raw %>% transmute(recordId=as.character(`_id`),caseNumber=N_EXPEDIENT,registerRaw=NUMERO_REGISTRE_GENERALITAT,
            registerKey=toupper(gsub("[[:space:]\u00a0]","",NUMERO_REGISTRE_GENERALITAT)),sourceBarriId=id2(CODI_BARRI),
            sourceBarriRaw=CODI_BARRI,sourceName=NOM_BARRI,lon=num(LONGITUD_X),lat=num(LATITUD_Y),beds=num(NUMERO_PLACES)) %>%
  mutate(missingNumber=is.na(registerKey)|registerKey=="",standardNumber=!missingNumber&grepl("^HUTB-[0-9]{6}$",registerKey),
         missingBarri=is.na(sourceBarriId),duplicateNumber=standardNumber&(duplicated(registerKey)|duplicated(registerKey,fromLast=TRUE)),
         validCoordinates=is.finite(lon)&is.finite(lat)&lon>=-180&lon<=180&lat>=-90&lat<=90)
ck("hut_case_numbers_unique",!anyDuplicated(hut$caseNumber))
hut$barriId <- hut$sourceBarriId
hut$spatialBarriId <- NA_character_
hut$spatialConflict <- FALSE
hut$spatialRecovered <- FALSE
hut$nearBoundary <- NA
hut$spatialStatus <- "not_yet_checked"
hut_quality <- list(rawRows=nrow(hut),missingNumber=sum(hut$missingNumber),missingBarri=sum(hut$missingBarri),
                    missingIntersection=sum(hut$missingNumber&hut$missingBarri),nonstandardNonempty=sum(!hut$missingNumber&!hut$standardNumber),
                    normalizedNumberChanges=sum(hut$registerKey!=hut$registerRaw,na.rm=TRUE),
                    duplicateNormalizedNumberRows=sum(hut$duplicateNumber),validity="Operating/legal validity is not established")

message("string-preserving platform panel")
required <- c("id","host_id","room_type","minimum_nights","latitude","longitude","neighbourhood_cleansed","last_scraped","number_of_reviews_ltm","last_review","license")
platform_list <- lapply(seq_along(dates),function(k) {
  p <- file.path(raw_root,"inside_airbnb",dates[k],"listings.csv.gz")
  x <- read_csv(p,col_types=cols(.default=col_character()),col_select=all_of(required),show_col_types=FALSE,progress=FALSE,trim_ws=FALSE)
  ck(paste0("platform",k,":exact_unique_id"),is.character(x$id)&&!anyNA(x$id)&&!anyDuplicated(x$id))
  ck(paste0("platform",k,":string_json_roundtrip"),identical(x$id,fromJSON(toJSON(x$id))))
  x <- x %>% transmute(snapshotIndex=k-1L,snapshot=dates[k],listingId=id,hostId=host_id,roomType=room_type,
       minimumNights=num(minimum_nights),lon=num(longitude),lat=num(latitude),sourceName=neighbourhood_cleansed,
       sourceBarriId=unname(name_map[name_key(neighbourhood_cleansed)]),actualScraped=last_scraped,reviewsLtm=num(number_of_reviews_ltm),lastReview=last_review,
       licenseRaw=license) %>% mutate(entire=roomType=="Entire home/apt",knownType=roomType %in% c("Entire home/apt","Private room","Shared room","Hotel room"),
       stayBand=case_when(minimumNights>=1&minimumNights<=30~"1-30",minimumNights>=31&minimumNights<=89~"31-89",minimumNights>=90~"90+",TRUE~"unknown"))
  ck(paste0("platform",k,":recognized_source_labels"),all(!is.na(x$sourceBarriId)))
  x
})
platform <- bind_rows(platform_list) %>% arrange(snapshotIndex,listingId)
ids_long <- platform$listingId[nchar(platform$listingId)>16|(nchar(platform$listingId)==16 & platform$listingId>"9007199254740991")]
id_proof <- list(type="character",recordsBeyondJavaScriptSafeInteger=length(ids_long),examples=head(unique(ids_long),4),
                 jsonQuoted=toJSON(head(unique(ids_long),4)),roundTrip=identical(ids_long,fromJSON(toJSON(ids_long))))
jwrite(id_proof,"audit/id_precision.json")
platform_dates <- platform %>% group_by(snapshotIndex,snapshot) %>% summarise(actualStart=min(actualScraped),actualEnd=max(actualScraped),records=n(),uniqueIds=n_distinct(listingId),.groups="drop")
composition <- platform %>% group_by(snapshotIndex,snapshot,roomType,stayBand) %>% summarise(records=n(),.groups="drop")
host_size <- platform %>% filter(entire,!is.na(hostId)) %>% count(snapshotIndex,hostId,name="entireListings")
host_structure <- host_size %>% group_by(snapshotIndex) %>% summarise(totalEntireListings=sum(entireListings),
         managedBy2Plus=sum(entireListings[entireListings>=2]),managedBy5Plus=sum(entireListings[entireListings>=5]),managedBy10Plus=sum(entireListings[entireListings>=10]),.groups="drop") %>% rename(entireListings=totalEntireListings)
for(k in 0:3) {
  counts<-host_size$entireListings[host_size$snapshotIndex==k]
  row<-host_structure[host_structure$snapshotIndex==k,]
  ck(paste0("host",k,":threshold_counts"),row$entireListings-row$managedBy2Plus==sum(counts==1) && row$managedBy10Plus<=row$managedBy5Plus && row$managedBy5Plus<=row$managedBy2Plus && row$managedBy2Plus<=row$entireListings)
}
cwrite(composition,"tables/platform_composition.csv");cwrite(host_structure,"tables/platform_account_structure.csv")
pair_rows <- list(); pair_summaries <- list()
for (k in 1:3) {
  a<-platform_list[[k]];b<-platform_list[[k+1L]]
  p<-full_join(a %>% select(listingId,hostA=hostId,roomA=roomType,lonA=lon,latA=lat),b %>% select(listingId,hostB=hostId,roomB=roomType,lonB=lon,latB=lat),by="listingId")
  p$inA<-p$listingId %in% a$listingId;p$inB<-p$listingId %in% b$listingId
  p$status<-ifelse(p$inA&p$inB,"reobserved",ifelse(p$inB,"only_later","only_earlier"))
  previous<-if(k>1)unique(platform$listingId[platform$snapshotIndex<k-1L])else character()
  p$reappearedAfterGap<-p$status=="only_later"&p$listingId %in% previous
  p$hostChanged<-p$inA&p$inB&!is.na(p$hostA)&!is.na(p$hostB)&p$hostA!=p$hostB
  p$roomChanged<-p$inA&p$inB&!is.na(p$roomA)&!is.na(p$roomB)&p$roomA!=p$roomB
  p$pairIndex<-k;p$earlier<-dates[k];p$later<-dates[k+1L]
  p$coordinateShiftMetres<-NA_real_
  valid<-p$inA&p$inB&is.finite(p$lonA)&is.finite(p$latA)&is.finite(p$lonB)&is.finite(p$latB)
  if(any(valid)) {
    aa<-st_transform(st_as_sf(p[valid,],coords=c("lonA","latA"),crs=4326),25831)
    bb<-st_transform(st_as_sf(p[valid,],coords=c("lonB","latB"),crs=4326),25831)
    p$coordinateShiftMetres[valid]<-as.numeric(st_distance(aa,bb,by_element=TRUE))
  }
  z<-list(pairIndex=k,earlier=dates[k],later=dates[k+1L],earlierCount=nrow(a),laterCount=nrow(b),
          reobserved=sum(p$status=="reobserved"),newlyObserved=sum(p$status=="only_later"),notReobserved=sum(p$status=="only_earlier"),
          reappearedAfterGap=sum(p$reappearedAfterGap),roomChanged=sum(p$roomChanged),hostChanged=sum(p$hostChanged),
          shiftedOver100m=sum(p$coordinateShiftMetres>100,na.rm=TRUE),shiftedOver500m=sum(p$coordinateShiftMetres>500,na.rm=TRUE),
          retention=100*sum(p$status=="reobserved")/nrow(a),netChange=nrow(b)-nrow(a))
  ck(paste0("pair",k,":id_net_identity"),z$netChange==z$newlyObserved-z$notReobserved)
  pair_rows[[k]]<-p %>% arrange(listingId);pair_summaries[[k]]<-z
}
pairs<-bind_rows(pair_rows)
cwrite(pairs,"audit/platform_pair_records.csv")
cwrite(platform %>% select(-licenseRaw),"audit/platform_panel.csv")
panel_roundtrip<-read_csv(file.path(out,"audit/platform_panel.csv"),col_types=cols(.default=col_character()),show_col_types=FALSE,progress=FALSE)
id_proof$csvListingRoundTrip<-identical(platform$listingId,panel_roundtrip$listingId)
id_proof$csvHostRoundTrip<-identical(platform$hostId,panel_roundtrip$hostId)
ck("string_ids_csv_roundtrip",id_proof$csvListingRoundTrip && id_proof$csvHostRoundTrip)
jwrite(id_proof,"audit/id_precision.json")
jwrite(list(platformDates=platform_dates,composition=composition,accountStructure=host_structure,pairs=pair_summaries,hut=hut_quality),"public/nonspatial_summary.json")

# Spatial processing and analysis continue below when an adopted boundary is supplied.
if(is.null(geometry_path)) {
  jwrite(list(stage="nonspatial",checks=checks,hut=hut_quality),"audit/quality.json")
  message("Non-spatial build complete; provide --geometry for the spatial research outputs")
  quit(status=0)
}
message("adopted geometry and point attribution")
geo<-st_read(geometry_path,quiet=TRUE)
if(!"id" %in% names(geo)) geo$id<-if("barri_id"%in%names(geo))id2(geo$barri_id)else id2(substr(geo$COD_BARRI,6,7))
geo$id<-id2(geo$id)
geo<-geo %>% arrange(id)
ck("geometry_73_unique_codes",nrow(geo)==73&&!anyDuplicated(geo$id)&&all(!is.na(geo$id)))
ck("geometry_valid",all(st_is_valid(geo)))
if(!"comparable"%in%names(geo))geo$comparable<-!geo$id%in%c("11","12")
geo$comparable<-as.logical(geo$comparable)
metric_geo<-st_transform(geo,25831)
city<-st_union(st_geometry(metric_geo))
geometry_hash<-hash_file(geometry_path)

attribute_points<-function(df) {
  valid<-is.finite(df$lon)&is.finite(df$lat)&abs(df$lat)<=90&abs(df$lon)<=180
  ans<-data.frame(row=seq_len(nrow(df)),spatialBarriId=NA_character_,spatialMatches=0L,x=NA_real_,y=NA_real_)
  if(any(valid)) {
    pts<-st_transform(st_as_sf(df[valid,],coords=c("lon","lat"),crs=4326),25831)
    hits<-st_intersects(pts,metric_geo)
    xy<-st_coordinates(pts)
    ans$x[valid]<-xy[,1];ans$y[valid]<-xy[,2]
    ans$spatialMatches[valid]<-lengths(hits)
    ans$spatialBarriId[valid]<-vapply(hits,function(v)if(length(v)==1)metric_geo$id[v]else NA_character_,character(1))
  }
  ans
}
ha<-attribute_points(hut)
hut$spatialBarriId<-ha$spatialBarriId
hut$spatialConflict<-!is.na(hut$sourceBarriId)&!is.na(hut$spatialBarriId)&hut$sourceBarriId!=hut$spatialBarriId
hut$spatialStatus<-ifelse(ha$spatialMatches==0,"outside_or_invalid",ifelse(ha$spatialMatches>1,"boundary_multiple","unique_inside"))
hut$nearBoundary<-FALSE
for(b in unique(na.omit(hut$spatialBarriId))) {
  ix<-which(hut$spatialBarriId==b)
  pts<-st_as_sf(data.frame(x=ha$x[ix],y=ha$y[ix]),coords=c("x","y"),crs=25831)
  hut$nearBoundary[ix]<-as.numeric(st_distance(pts,st_boundary(metric_geo[metric_geo$id==b,])))<10
}
recover<-hut$missingBarri & !is.na(hut$spatialBarriId) & !hut$nearBoundary
hut$barriId[recover]<-hut$spatialBarriId[recover]
hut$spatialRecovered<-recover
hut$status<-case_when(hut$missingNumber~"pending_missing_identifier",!hut$standardNumber~"pending_nonstandard_identifier",
       hut$duplicateNumber~"pending_duplicate_identifier",is.na(hut$barriId)~"pending_geography",TRUE~"included_registration")
hut$qualityFlag<-case_when(hut$spatialConflict~"source_geometry_conflict_source_code_retained",hut$spatialRecovered~"missing_code_spatially_recovered",
       hut$nearBoundary~"within_10m_of_boundary",hut$spatialStatus!="unique_inside"~hut$spatialStatus,TRUE~"source_code_matches_geometry")
ck("hut_all_records_accounted",sum(table(hut$status))==nrow(hut))
ck("hut_included_unique",!anyDuplicated(hut$registerKey[hut$status=="included_registration"]))
hut_quality$spatiallyRecovered<-sum(recover)
hut_quality$sourceGeometryConflicts<-sum(hut$spatialConflict)
hut_quality$nearBoundary10m<-sum(hut$nearBoundary)
hut_quality$included<-sum(hut$status=="included_registration")
hut_quality$pending<-sum(hut$status!="included_registration")
hut_quality$statusCounts<-as.list(table(hut$status))
hut_quality$unattributed<-sum(is.na(hut$barriId))
cwrite(hut,"audit/hut_record_disposition.csv")
cwrite(hut %>% filter(status!="included_registration"|spatialConflict|spatialRecovered),"audit/hut_review_records.csv")
hut_counts<-hut %>% filter(!is.na(barriId)) %>% group_by(id=barriId) %>% summarise(
  hutCount=sum(status=="included_registration"),hutPending=sum(status!="included_registration"),
  hutAllRecords=n(),hutStrictGeometry=sum(status=="included_registration" & !spatialConflict),
  hutBeds=sum(beds[status=="included_registration"],na.rm=TRUE),missingBeds=sum(is.na(beds)&status=="included_registration"),.groups="drop")

pa<-attribute_points(platform)
platform$spatialBarriId<-pa$spatialBarriId;platform$x<-pa$x;platform$y<-pa$y
platform$inCity<-pa$spatialMatches>=1
platform$spatialConflict<-!is.na(platform$spatialBarriId)&platform$sourceBarriId!=platform$spatialBarriId
platform$spatialStatus<-ifelse(pa$spatialMatches==0,"outside_or_invalid",ifelse(pa$spatialMatches>1,"boundary_multiple","unique_inside"))
# The first valid in-city position anchors an explicitly retrospective ID map.
refs<-platform %>% filter(inCity,is.finite(x),is.finite(y)) %>% arrange(snapshotIndex,listingId) %>% distinct(listingId,.keep_all=TRUE) %>%
  select(listingId,refX=x,refY=y,referenceSnapshot=snapshot)
platform<-left_join(platform,refs,by="listingId")
spatial_platform<-platform %>% group_by(snapshotIndex,snapshot) %>% summarise(records=n(),currentMapped=sum(inCity),currentUnmapped=sum(!inCity),
          fixedReferenceMapped=sum(!is.na(refX)),sourceGeometryConflicts=sum(spatialConflict),multipleMatches=sum(spatialStatus=="boundary_multiple"),.groups="drop")
cwrite(platform %>% select(snapshotIndex,snapshot,listingId,sourceBarriId,spatialBarriId,spatialStatus,spatialConflict,referenceSnapshot),"audit/platform_spatial_attribution.csv")
cwrite(spatial_platform,"tables/platform_spatial_coverage.csv")

geo_write<-function(x,path) {
  x<-st_transform(x,4326)
  st_write(x,file.path(out,path),driver="GeoJSON",delete_dsn=TRUE,quiet=TRUE,layer_options=c("RFC7946=YES","COORDINATE_PRECISION=7"))
}
grid_key<-function(x,y,size=500,shift=c(0,0)) {
  valid<-is.finite(x)&is.finite(y)
  result<-rep(NA_character_,length(x))
  result[valid]<-paste0("g",size,"_",shift[1],"_",shift[2],"_",floor((x[valid]-shift[1])/size),"_",floor((y[valid]-shift[2])/size))
  result
}
platform$currentCell<-grid_key(platform$x,platform$y);platform$currentCell[!platform$inCity]<-NA_character_
platform$referenceCell<-grid_key(platform$refX,platform$refY)
bb<-st_bbox(metric_geo)
xx<-seq(floor(bb[1]/500),floor(bb[3]/500));yy<-seq(floor(bb[2]/500),floor(bb[4]/500))
grid_index<-expand_grid(ix=xx,iy=yy) %>% arrange(ix,iy)
polys<-lapply(seq_len(nrow(grid_index)),function(k){x<-grid_index$ix[k]*500;y<-grid_index$iy[k]*500;st_polygon(list(matrix(c(x,y,x+500,y,x+500,y+500,x,y+500,x,y),ncol=2,byrow=TRUE)))})
grid<-st_sf(id=grid_key(grid_index$ix*500+1,grid_index$iy*500+1),geometry=st_sfc(polys,crs=25831))
grid<-grid[lengths(st_intersects(grid,city))>0,]
grid<-suppressWarnings(st_intersection(grid,st_sf(geometry=city)))
grid<-grid[as.numeric(st_area(grid))>0,]
grid$coveredAreaM2<-as.numeric(st_area(grid))
grid_before_ids<-grid$id;grid_before_areas<-grid$coveredAreaM2
# Clipping may retain zero-area line fragments inside GeometryCollections.
# Keep the polygonal part for vector tiles; retain the already calculated area.
grid<-suppressWarnings(st_collection_extract(grid,'POLYGON'))
grid<-suppressWarnings(st_cast(grid,'MULTIPOLYGON'))
ck("grid_polygon_extraction_preserves_rows_and_area",identical(grid$id,grid_before_ids) && identical(grid$coveredAreaM2,grid_before_areas) &&
   all(abs(as.numeric(st_area(grid))-grid_before_areas)<1e-6))
ck("grid_523_valid_nonempty_multipolygons",nrow(grid)==523 && all(st_geometry_type(grid)=='MULTIPOLYGON') && all(st_is_valid(grid)) && !any(st_is_empty(grid)))
ck("grid_unique_ids",!anyDuplicated(grid$id))
for(k in 0:3) {
  z<-platform %>% filter(snapshotIndex==k,!is.na(currentCell)) %>% group_by(id=currentCell) %>% summarise(n=n(),entire=sum(entire,na.rm=TRUE),known=sum(knownType),short=sum(stayBand=="1-30"),.groups="drop")
  rr<-platform %>% filter(snapshotIndex==k,!is.na(referenceCell)) %>% count(id=referenceCell,name="refN")
  m<-match(grid$id,z$id);mr<-match(grid$id,rr$id)
  for(field in c("n","entire","known","short"))grid[[paste0(field,k)]]<-replace_na(z[[field]][m],0L)
  grid[[paste0("share",k)]]<-ifelse(grid[[paste0("known",k)]]>0,100*grid[[paste0("entire",k)]]/grid[[paste0("known",k)]],NA_real_)
  grid[[paste0("refN",k)]]<-replace_na(rr$refN[mr],0L)
  ck(paste0("grid",k,":current_total"),sum(grid[[paste0("n",k)]])==sum(platform$inCity&platform$snapshotIndex==k))
  ck(paste0("grid",k,":reference_total"),sum(grid[[paste0("refN",k)]])==sum(platform$snapshotIndex==k&!is.na(platform$referenceCell)))
}
ref_keys<-platform %>% distinct(listingId,referenceCell)
for(k in 1:3) {
  z<-pairs %>% filter(pairIndex==k) %>% left_join(ref_keys,by="listingId") %>% filter(!is.na(referenceCell)) %>% group_by(id=referenceCell) %>%
    summarise(new=sum(status=="only_later"),lost=sum(status=="only_earlier"),again=sum(status=="reobserved"),.groups="drop")
  m<-match(grid$id,z$id)
  for(field in c("new","lost","again"))grid[[paste0(field,k)]]<-replace_na(z[[field]][m],0L)
  ck(paste0("grid_pair",k,":id_identity"),all(grid[[paste0("refN",k)]]-grid[[paste0("refN",k-1)]]==grid[[paste0("new",k)]]-grid[[paste0("lost",k)]]))
}
# Serialize the already validated polygon parts directly. GDAL's RFC7946
# precision/fixup pass can reintroduce zero-area fragments as collections.
grid_wgs<-st_transform(grid %>% arrange(id),4326)
grid_wgs_before<-grid_wgs
# Coordinate transformation can create microscopic topology artefacts.
# Repair display geometry on a 1e-12-degree grid; analytical areas stay fixed.
grid_wgs<-suppressWarnings(st_cast(st_collection_extract(st_make_valid(st_set_precision(grid_wgs,1e12)),'POLYGON'),'MULTIPOLYGON'))
ck("grid_display_repair_preserves_all_properties",identical(st_drop_geometry(grid_wgs),st_drop_geometry(grid_wgs_before)))
display_areas<-as.numeric(st_area(st_transform(grid_wgs,25831)))
cwrite(tibble(id=grid_wgs$id,analyticalAreaM2=grid_wgs$coveredAreaM2,displayAreaM2=display_areas,
   displayAreaDifferenceM2=display_areas-grid_wgs$coveredAreaM2,
   longitudeLatitudeValidBeforeRepair=st_is_valid(grid_wgs_before)),"audit/grid_geometry_export.csv")
orient_ring<-function(ring,outer) {
  closed<-rbind(ring,ring[1,,drop=FALSE])
  signed<-sum(closed[-nrow(closed),1]*closed[-1,2]-closed[-1,1]*closed[-nrow(closed),2])
  if((outer&&signed<0)||(!outer&&signed>0))ring[nrow(ring):1,,drop=FALSE]else ring
}
grid_features<-lapply(seq_len(nrow(grid_wgs)),function(k) {
  coords<-lapply(st_geometry(grid_wgs)[[k]],function(poly)lapply(seq_along(poly),function(j)orient_ring(poly[[j]],j==1)))
  list(type='Feature',properties=as.list(st_drop_geometry(grid_wgs[k,])),geometry=list(type='MultiPolygon',coordinates=coords))
})
jwrite(list(type='FeatureCollection',features=grid_features),"public/grid.geojson")
grid_export_check<-st_read(file.path(out,"public/grid.geojson"),quiet=TRUE)
ck("grid_export_valid_pure_polygons",nrow(grid_export_check)==523 && all(st_geometry_type(grid_export_check)%in%c('POLYGON','MULTIPOLYGON')) &&
   all(st_is_valid(grid_export_check)) && !any(st_is_empty(grid_export_check)))
cwrite(st_drop_geometry(grid),"tables/grid_500m.csv")

message("indicators and common-sample overlap")
neighbourhoods<-names %>% left_join(housing %>% select(id=barriId,year,housing) %>% mutate(year=paste0("housing",year)) %>% pivot_wider(names_from=year,values_from=housing),by="id") %>%
   left_join(hut_counts,by="id")
for(v in c("hutCount","hutPending","hutAllRecords","hutStrictGeometry","hutBeds","missingBeds"))neighbourhoods[[v]]<-replace_na(neighbourhoods[[v]],0L)
for(y in 2019:2025) {
  z<-rent_wide %>% filter(geography=="neighbourhood",year==y) %>% select(id,rentM2,rentMonth,contracts)
  names(z)[-1]<-paste0(c("rent","rentMonth","contracts"),y)
  neighbourhoods<-left_join(neighbourhoods,z,by="id")
}
neighbourhoods<-neighbourhoods %>% mutate(hutIntensity=1000*hutCount/housing2026,hutInclusiveIntensity=1000*hutAllRecords/housing2026,
       hutStrictIntensity=1000*hutStrictGeometry/housing2026,rentChange=100*(rent2025/rent2022-1),contractIntensity=1000*contracts2025/housing2025,
       comparable=geo$comparable[match(id,geo$id)],validRent2025=is.finite(rent2025)&contracts2025>=30,
       validRentChange=is.finite(rent2025)&is.finite(rent2022)&rent2022>0&contracts2025>=30&contracts2022>=30,
       validContractActivity=is.finite(contracts2025)&contracts2025>=0&housing2025>0,
       qualityFlag=case_when(!comparable~"aei_scope_not_confirmed",!validRent2025~"price_contract_count_below_30",hutPending>0~"pending_registry_records_retained_in_audit",TRUE~"comparable"))
dec_platform<-platform %>% filter(snapshotIndex==1) %>% group_by(id=sourceBarriId) %>% summarise(platform2025=n(),platformEntire2025=sum(entire,na.rm=TRUE),.groups="drop")
neighbourhoods<-left_join(neighbourhoods,dec_platform,by="id") %>% mutate(platform2025=replace_na(platform2025,0L),platformEntire2025=replace_na(platformEntire2025,0L),platformIntensity2025=1000*platformEntire2025/housing2025)
overlap_calc<-function(data,dimension="level",share=.25,minimum=30,base=2022,hut_field="hutIntensity",allow_aei=FALSE) {
  y<-if(dimension=="level")data$rent2025 else 100*(data$rent2025/data[[paste0("rent",base)]]-1)
  valid<-is.finite(data[[hut_field]])&is.finite(y)&data$contracts2025>=minimum&data$housing2026>0
  if(dimension=="change")valid<-valid&data[[paste0("contracts",base)]]>=minimum&data[[paste0("rent",base)]]>0
  if(!allow_aei)valid<-valid&data$comparable
  valid[is.na(valid)]<-FALSE
  x<-data[[hut_field]][valid]; yy<-y[valid]
  ck("overlap_nonempty",length(x)>2)
  tx<-unname(quantile(x,1-share,type=7));ty<-unname(quantile(yy,1-share,type=7))
  T<-x>=tx;P<-yy>=ty
  classes<-rep("unavailable",nrow(data));classes[valid]<-ifelse(T&P,"both",ifelse(T,"tourism",ifelse(P,"rent","neither")))
  selected<-which(valid)[P];city_den<-sum(data$hutCount);sample_den<-sum(data$hutCount[valid]);num_hut<-sum(data$hutCount[selected])
  list(summary=list(dimension=dimension,highShare=share,minimumContracts=minimum,baseYear=if(dimension=="change")base else NULL,
       tourismMetric=hut_field,allowUnconfirmedAei=allow_aei,sampleN=sum(valid),excludedIds=data$id[!valid],hutThreshold=tx,rentThreshold=ty,
       tourismHigh=sum(T),rentHigh=sum(P),intersection=sum(T&P),union=sum(T|P),jaccard=if(sum(T|P))sum(T&P)/sum(T|P)else NA_real_,
       overlapShareTourism=100*sum(T&P)/sum(T),overlapShareRent=100*sum(T&P)/sum(P),
       rentHighHutCount=num_hut,cityIncludedHutDenominator=city_den,commonSampleHutDenominator=sample_den,
       hutOutsideCommonSample=city_den-sample_den,rentHighHutShareCity=100*num_hut/city_den,rentHighHutShareCommon=100*num_hut/sample_den,
       homesRentHighOutsideTourism=sum(data$housing2026[which(valid)[P&!T]]),spearman=unname(cor(x,yy,method="spearman"))),
       classes=classes,valid=valid,y=y)
}
level<-overlap_calc(neighbourhoods);change<-overlap_calc(neighbourhoods,"change")
neighbourhoods$overlapClass<-level$classes;neighbourhoods$changeClass<-change$classes

message("sensitivity and transparent candidate selection")
sensitivity<-list(); class_variants<-list()
add_sensitivity<-function(label,dimension="level",...) {
  z<-overlap_calc(neighbourhoods,dimension,...)
  baseline<-if(dimension=="level")level else change
  shared<-z$valid&baseline$valid
  z$summary$scenario<-label
  z$summary$sharedSampleN<-sum(shared)
  z$summary$classRetention<-if(sum(shared))100*mean(z$classes[shared]==baseline$classes[shared])else NA_real_
  sensitivity[[length(sensitivity)+1L]]<<-z$summary
  class_variants[[paste0(label,"_",dimension)]]<<-z$classes
}
for(d in c("level","change")) {
  for(s in c(.20,.25,.33))add_sensitivity(paste0("share_",s),d,share=s)
  for(m in c(15,50))add_sensitivity(paste0("contracts_",m),d,minimum=m)
  add_sensitivity("include_pending_records",d,hut_field="hutInclusiveIntensity")
  add_sensitivity("exclude_coordinate_conflicts",d,hut_field="hutStrictIntensity")
  add_sensitivity("exclude_aei_11_12",d,allow_aei=FALSE)
  add_sensitivity("unconfirmed_aei_comparison_only",d,allow_aei=TRUE)
  add_sensitivity("platform_entire_dec2025",d,hut_field="platformIntensity2025")
}
for(b in c(2019,2023))add_sensitivity(paste0("base_",b),"change",base=b)
sensitivity_table<-bind_rows(lapply(sensitivity,function(z)as_tibble(z[!names(z)%in%c("excludedIds","baseYear")],.name_repair="unique") %>% mutate(baseYear=if(is.null(z$baseYear))NA_integer_ else z$baseYear)))
cwrite(sensitivity_table,"tables/overlap_sensitivity.csv")
neighbourhoods$thresholdStable<-vapply(seq_len(nrow(neighbourhoods)),function(i){v<-vapply(c("share_0.2_level","share_0.25_level","share_0.33_level"),function(k)class_variants[[k]][i],character(1));length(unique(v))==1&&v[1]!="unavailable"},logical(1))
valid_cases<-neighbourhoods %>% filter(level$valid)
rent_sd<-sd(valid_cases$rent2025)
case_candidates<-cross_join(valid_cases %>% select(a=id,aName=name,aRent=rent2025,aHut=hutIntensity,aClass=overlapClass,aStable=thresholdStable),
                            valid_cases %>% select(b=id,bName=name,bRent=rent2025,bHut=hutIntensity,bClass=overlapClass,bStable=thresholdStable)) %>%
   filter(a<b) %>% mutate(rentGap=abs(aRent-bRent),hutGap=abs(aHut-bHut),
       oppositeHutGroup=(aClass%in%c("both","tourism"))!=(bClass%in%c("both","tourism")),stable=aStable&bStable) %>%
   filter(rentGap<=.5*rent_sd,oppositeHutGroup) %>% arrange(desc(stable),desc(hutGap),rentGap,a,b) %>% mutate(rank=row_number())
case_rule<-"rent gap <= 0.5 common-sample SD; opposite HUT high groups; prefer threshold-stable pairs, then larger HUT gap, smaller rent gap, ascending IDs"
if(nrow(case_candidates)==0) {
  hut_sd<-sd(valid_cases$hutIntensity)
  case_candidates<-cross_join(valid_cases %>% select(a=id,aName=name,aRent=rent2025,aHut=hutIntensity,aClass=overlapClass,aStable=thresholdStable),
       valid_cases %>% select(b=id,bName=name,bRent=rent2025,bHut=hutIntensity,bClass=overlapClass,bStable=thresholdStable)) %>%
    filter(a<b) %>% mutate(rentGap=abs(aRent-bRent),hutGap=abs(aHut-bHut),
      oppositeRentGroup=(aClass%in%c("both","rent"))!=(bClass%in%c("both","rent")),stable=aStable&bStable) %>%
    filter(hutGap<=.5*hut_sd,oppositeRentGroup) %>% arrange(desc(stable),desc(rentGap),hutGap,a,b) %>% mutate(rank=row_number())
  case_rule<-"Fallback after no primary pair: HUT gap <= 0.5 common-sample SD; opposite rent-high groups; prefer threshold-stable pairs, then larger rent gap, smaller HUT gap, ascending IDs"
}
cwrite(case_candidates,"tables/case_candidates.csv")
chosen_a<-arg("case-a");chosen_b<-arg("case-b")
chosen_valid<-!is.null(chosen_a)&&!is.null(chosen_b)&&any((case_candidates$a==chosen_a&case_candidates$b==chosen_b)|(case_candidates$b==chosen_a&case_candidates$a==chosen_b))
if(!is.null(chosen_a)||!is.null(chosen_b))ck("selected_case_pair_is_eligible",chosen_valid)
neighbourhoods$caseFlag<-if(chosen_valid)neighbourhoods$id%in%c(chosen_a,chosen_b)else FALSE
case_evidence_path<-arg("case-evidence")
case_evidence<-if(!is.null(case_evidence_path))fromJSON(case_evidence_path,simplifyVector=FALSE)else list()
evidence_confirmed<-chosen_valid && length(case_evidence)>0 && all(c(chosen_a,chosen_b)%in%vapply(case_evidence$cases,function(x)x$id,character(1)))
case_records<-function(ids)lapply(ids,function(case_id)as.list(neighbourhoods %>% filter(.data$id==.env$case_id) %>% select(id,name,rent2025,rent2022,rentChange,contracts2025,contracts2022,housing2026,hutCount,hutPending,hutIntensity,overlapClass,changeClass,thresholdStable,qualityFlag)))
case_summary<-list(status=if(evidence_confirmed)"eligible_pair_selected_with_public_place_evidence"else if(chosen_valid)"eligible_pair_selected_for_documented_case_review"else"numeric_candidates_await_place_specific_evidence",rule=case_rule,rentGapLimit=.5*rent_sd,
        candidateCount=nrow(case_candidates),candidates=head(case_candidates,25),selected=if(chosen_valid)case_records(c(chosen_a,chosen_b))else list())
case_summary$thresholdStableMeaning<-"Level-class membership unchanged across 20%, 25%, and 33% high-share cutoffs; not stability across every sensitivity or evidence of causality"
case_summary$evidence<-case_evidence
if(chosen_valid)ck("selected_case_records_are_two_single_objects",length(case_summary$selected)==2 && identical(vapply(case_summary$selected,function(x)x$id,character(1)),c(chosen_a,chosen_b)))

grid_sensitivity<-list();moving_ids<-unique(pairs$listingId[!is.na(pairs$coordinateShiftMetres)&pairs$coordinateShiftMetres>100])
grid_scenarios<-list(list(label="500m",size=500,shift=c(0,0),mode="current",filter="all"),list(label="1000m",size=1000,shift=c(0,0),mode="current",filter="all"),
 list(label="shift_x_250",size=500,shift=c(250,0),mode="current",filter="all"),list(label="shift_y_250",size=500,shift=c(0,250),mode="current",filter="all"),
 list(label="shift_xy_250",size=500,shift=c(250,250),mode="current",filter="all"),list(label="fixed_reference",size=500,shift=c(0,0),mode="reference",filter="all"),
 list(label="exclude_shift_over_100m",size=500,shift=c(0,0),mode="current",filter="stable"),list(label="review_in_last_12m",size=500,shift=c(0,0),mode="current",filter="reviewed"))
for(s in grid_scenarios)for(k in 0:3) {
  z<-platform %>% filter(snapshotIndex==k)
  if(s$filter=="stable")z<-z %>% filter(!listingId%in%moving_ids)
  if(s$filter=="reviewed")z<-z %>% filter(reviewsLtm>0)
  keys<-if(s$mode=="reference")grid_key(z$refX,z$refY,s$size,s$shift)else grid_key(ifelse(z$inCity,z$x,NA),z$y,s$size,s$shift)
  counts<-sort(table(keys),decreasing=TRUE)
  topn<-if(length(counts))ceiling(.1*length(counts))else 0
  grid_sensitivity[[length(grid_sensitivity)+1L]]<-list(scenario=s$label,snapshotIndex=k,snapshot=dates[k+1],mapped=sum(counts),unmapped=sum(is.na(keys)),nonemptyCells=length(counts),
       maximumCellCount=if(length(counts))max(counts)else 0,topDecileNonemptyCellShare=if(length(counts))100*sum(head(counts,topn))/sum(counts)else NA_real_)
}
cwrite(bind_rows(grid_sensitivity),"tables/grid_sensitivity.csv")
cwrite(neighbourhoods,"tables/neighbourhoods.csv")
geo_out<-geo %>% select(id,geometry) %>% left_join(neighbourhoods,by="id")
geo_write(geo_out,"public/neighbourhoods.geojson")
hut_public<-hut %>% filter(status=="included_registration",validCoordinates,spatialStatus=="unique_inside") %>%
   transmute(id=paste0("h",recordId),barriId,beds,qualityFlag,lon,lat)
geo_write(st_as_sf(hut_public,coords=c("lon","lat"),crs=4326),"public/hut.geojson")

summary<-list(meta=list(schemaVersion="1.0",studyConfigHash=if(!is.null(config_path))hash_file(config_path)else NULL,
       geometryHash=geometry_hash,comparison="Current 2026 HUT register and cadastral residential units alongside 2025 registered rents; not a same-year causal estimate",
       currency="EUR",rentUnit="EUR/m2/month",percentScale="0-100",classification=c("both","tourism","rent","neither","unavailable"),
       geometryComparable=sum(neighbourhoods$comparable),unconfirmedScopeIds=neighbourhoods$id[!neighbourhoods$comparable]),
   totals=list(hutRaw=nrow(hut),hutIncluded=hut_quality$included,hutPending=hut_quality$pending,housing2025=sum(neighbourhoods$housing2025),housing2026=sum(neighbourhoods$housing2026),
       latestPlatform=nrow(platform_list[[4]]),neighbourhoods=73),
   charts=list(cityRent=rent_wide %>% filter(geography=="city") %>% select(year,rentM2,rentMonth,contracts),
       neighbourhoodRent=rent_wide %>% filter(geography=="neighbourhood") %>% select(id,name,year,rentM2,rentMonth,contracts),
       platformComposition=composition,hostStructure=host_structure,contractCoverage=coverage,platformTransitions=pair_summaries,
       scatter=neighbourhoods %>% select(id,name,hutIntensity,rent2025,rentChange,contracts2025,overlapClass,changeClass,comparable,validRent2025,validRentChange)),
   rentYears=2019:2025,overlap=list(level=level$summary,change=change$summary),
   sensitivity=list(overlap=sensitivity,grid=grid_sensitivity),cases=case_summary,platformDates=platform_dates,
   dataQuality=list(hut=hut_quality,platformSpatial=spatial_platform,idPrecision=id_proof,
       unresolvedGeography=neighbourhoods$id[!neighbourhoods$comparable],contractGeolocation=coverage,
       warnings=c("AEI scope flags govern comparability; excluded areas retain their original figures",
         "Pending HUT identifiers remain in the audit and inclusive-record sensitivity, not the primary count",
         "Calendar availability is not occupancy; listing disappearance is not residential return",
         "City and neighbourhood contract totals differ because geolocation coverage differs",
         "Fixed-reference maps retrospectively anchor IDs and differ from current-position maps")))
jwrite(summary,"public/summary.json")
jwrite(list(stages=c("source validation","data harmonisation","spatial aggregation","sensitivity analysis","case selection","web export"),checks=checks,hut=hut_quality,platformSpatial=spatial_platform,
            unconfirmedAei=neighbourhoods$id[!neighbourhoods$comparable],caseSelectionStatus=case_summary$status),"audit/quality.json")
environment<-list(R=as.character(getRversion()),packages=setNames(lapply(c("sf","dplyr","tidyr","readr","readxl","jsonlite","digest"),function(p)as.character(packageVersion(p))),c("sf","dplyr","tidyr","readr","readxl","jsonlite","digest")),
                  spatialLibraries=as.list(sf_extSoftVersion()))
jwrite(environment,"audit/environment.json")
message("Complete: ",out,"; common samples ",level$summary$sampleN,"/",change$summary$sampleN,"; HUT included ",hut_quality$included)
