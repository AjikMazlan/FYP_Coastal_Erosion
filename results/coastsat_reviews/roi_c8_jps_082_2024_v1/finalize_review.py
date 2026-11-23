import os
os.environ['MPLBACKEND']='Agg'
os.environ['GDAL_PAM_ENABLED']='NO'
import csv,hashlib,json,pickle,sys,warnings
from pathlib import Path
from collections import Counter
warnings.filterwarnings('ignore')
import numpy as np
from scipy.spatial import cKDTree
from skimage.measure import find_contours
coast=Path(r'D:\CoastSat-master')
sys.path.insert(0,str(coast))
from coastsat import SDS_preprocess,SDS_shoreline,SDS_tools,SDS_transects

root=Path.cwd()
output=root/'results/coastsat_reviews/roi_c8_jps_082_2024_v1'
output.mkdir(parents=True,exist_ok=True)
hashes={}
def read_protected(path):
    data=Path(path).read_bytes()
    hashes[str(Path(path).resolve())]=hashlib.sha256(data).hexdigest()
    return data
def stats(points,transect,qc):
    origin,end=transect;direction=(end-origin)/np.linalg.norm(end-origin)
    perpendicular=np.array([-direction[1],direction[0]])
    if len(points):
        relative=points-origin
        close=(np.abs(relative@perpendicular)<=qc['along_dist'])&(np.linalg.norm(relative,axis=1)<=1000)
        chain=relative[close]@direction
        chain=chain[chain>=qc['min_chainage']]
    else: chain=np.empty(0)
    n=len(chain)
    median=float(np.median(chain)) if n else None
    std=float(np.std(chain)) if n else None
    spread=float(np.ptp(chain)) if n else None
    passed=bool(n>=qc['min_points'] and std<=qc['max_std'] and spread<=qc['max_range'] and 0<=median<=np.linalg.norm(end-origin))
    return {'n':n,'std':std,'range':spread,'median':median,'valid':passed}
def filter_mask(points,mask,geo,epsg,distance):
    if not len(points) or not mask.any():return points
    coords=SDS_tools.convert_epsg(SDS_tools.convert_pix2world(np.argwhere(mask),geo),epsg,32648)
    return points[cKDTree(coords).query(points)[0]>=distance]
empty=np.empty((0,2))
all_reports={}

work=root/'results/shoreline_pipeline/monthly_v1/roi_c8_jps_082'
before=json.loads((output/'source_hashes_before.json').read_text())
def check_sources():
    changed=[path for path,digest in before.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest]
    assert not changed,changed
    return {'files_checked':len(before),'changed_files':changed}
check_sources()
protocol=json.loads((work/'protocol.json').read_text());qc=protocol['intersection_qc'];site=protocol['site']
features=json.loads((root/site['transects']).read_text())['features']
transects={str(f['properties']['name']):np.asarray(f['geometry']['coordinates'],dtype=float) for f in features}
original=list(csv.DictReader((output/'measurements_original_2024.csv').read_text(encoding='utf-8-sig').splitlines()))
assert len(original)==225
scenes=json.loads((output/'scenes.json').read_text())
decisions=json.loads((output/'visual_decisions.json').read_text())
assert len(scenes)==len(decisions)==45
decision_by_index={d['scene_index']:d for d in decisions}
original_by_key={(r['Source_File'],r['Transect_ID']):r for r in original}
assert len(original_by_key)==len(original)
def qc_failure(value):
    codes=[]
    if value['n']<qc['min_points']:codes.append('min_points')
    if value['std'] is not None and value['std']>qc['max_std']:codes.append('max_std')
    if value['range'] is not None and value['range']>qc['max_range']:codes.append('max_range')
    if value['median'] is not None and not 0<=value['median']<=300.000001:codes.append('transect_bounds')
    return ';'.join(codes)
def number(v):
    return '' if v is None else f'{v:.9f}'
review_by_key={};audit_by_key={};component_audit=[];scene_results=[]
for scene in scenes:
    decision=decision_by_index[scene['index']]
    ids=decision['selected_component_ids']
    comps={c['id']:c for c in scene['components']}
    assert set(ids)<=set(comps),(scene['index'],ids)
    chosen=[np.asarray(comps[c]['points'],dtype=float) for c in ids]
    merged=np.vstack(chosen) if chosen else empty
    official=SDS_transects.compute_intersection_QC({'shorelines':[merged]},transects,qc)
    values={}
    for tid,t in transects.items():
        v=stats(merged,t,qc);values[tid]=v
        passed=bool(np.isfinite(official[tid][0]) and 0<=official[tid][0]<=np.linalg.norm(t[1]-t[0]))
        assert v['valid']==passed
        if passed:assert np.isclose(v['median'],official[tid][0])
        key=(scene['filename'],tid);old=original_by_key[key]
        old_valid=old['Valid']=='True'
        new=dict(old);new['Valid']=str(passed);new['Cross_Shore_Distance_m']=f"{official[tid][0]:.6f}" if passed else ''
        assert new['Tide_Corrected']=='False'
        review_by_key[key]=new
        if passed:result='accepted_sea_contour_qc_pass'
        elif not ids:result='rejected_visual_or_no_usable_sea_component'
        else:result='rejected_original_qc'
        audit_by_key[key]={
            'Date':old['Date'],'Transect_ID':tid,'Satellite':old['Satellite'],'Source_File':old['Source_File'],
            'Source_Image_Path':scene['image_path'],'Scene_Index':scene['index'],
            'Selected_Component_IDs':';'.join(map(str,ids)),'Review_Result':result,'Visual_Reason':decision['visual_reason'],
            'QC_Failure':qc_failure(v) if ids else 'no_accepted_sea_component',
            'QC_Point_Count':v['n'],'QC_Std_m':number(v['std']),'QC_Range_m':number(v['range']),
            'QC_Median_m':number(v['median']),'Reviewed_Position_m':new['Cross_Shore_Distance_m'],'Reviewed_Valid':str(passed),
            'Original_Position_m':old['Cross_Shore_Distance_m'],'Original_Valid':old['Valid'],
            'Original_Combined_Point_Count':scene['original_qc'][tid]['n'],
            'Original_Combined_Std_m':number(scene['original_qc'][tid]['std']),
            'Original_Combined_Range_m':number(scene['original_qc'][tid]['range']),
            'Image_Cloud_Fraction':number(scene['cloud_fraction']),'MNDWI_Threshold_Original':number(scene['mndwi_threshold']),
            'Reference_Buffer_m':100,'Min_Contour_Length_m':200,'Cloud_Distance_m':300,'Nodata_Distance_m':30,
            'Along_Dist_m':qc['along_dist'],'Min_Points':qc['min_points'],'Max_Std_m':qc['max_std'],
            'Max_Range_m':qc['max_range'],'Multiple_Intersection':qc['multiple_inter'],
            'Review_Method':'manual_visual_whole_component_selection','Review_Image':scene['review_image']}
    for ci,c in comps.items():
        selected=ci in ids
        reason=decision['rejected_component_reasons'].get(str(ci))
        if selected:reason=decision['visual_reason']
        elif not reason:
            if any(x['n'] for x in c['qc'].values()):
                reason='Kontur pada sisi darat jalur pasir, bukan sempadan pasir dengan laut terbuka; ditolak walaupun sesetengah persilangan lulus QC.'
            else:
                reason='Komponen tidak melintasi koridor T1-T5 dengan titik yang mencukupi selepas tapisan asal; tidak boleh mengisi ukuran.'
        for tid,v in c['qc'].items():
            component_audit.append({'Date':scene['date'],'Transect_ID':tid,'Source_File':scene['filename'],
                'Source_Image_Path':scene['image_path'],'Scene_Index':scene['index'],'Component_ID':ci,
                'Selected_Visual':selected,'Selection_Or_Rejection_Reason':reason,
                'Length_Before_Cloud_m':number(c['length_before_cloud_m']),
                'Point_Count':v['n'],'Std_m':number(v['std']),'Range_m':number(v['range']),'Median_m':number(v['median']),
                'Intersection_QC_Pass':v['valid'],'QC_Failure':qc_failure(v),'Review_Image':scene['review_image']})
    scene_results.append({'index':scene['index'],'source_file':scene['filename'],'selected_component_ids':ids,
         'valid_transects':[tid for tid,v in values.items() if v['valid']],'reason':decision['visual_reason']})
ordered_keys=[(r['Source_File'],r['Transect_ID']) for r in original]
reviewed=[review_by_key[k] for k in ordered_keys];audits=[audit_by_key[k] for k in ordered_keys]
assert set(review_by_key)==set(original_by_key)
def save_csv(path,rows,columns=None):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns or list(rows[0]))
        writer.writeheader();writer.writerows(rows)
save_csv(output/'measurements_reviewed_2024.csv',reviewed,list(original[0]))
save_csv(output/'review_audit_2024.csv',audits)
save_csv(output/'component_audit_2024.csv',component_audit)
coverage=[]
for tid in transects:
    b=sorted({r['Date'][:7] for r in original if r['Transect_ID']==tid and r['Valid']=='True'})
    a=sorted({r['Date'][:7] for r in reviewed if r['Transect_ID']==tid and r['Valid']=='True'})
    original_daily=sum(r['Transect_ID']==tid and r['Valid']=='True' for r in original)
    reviewed_daily=sum(r['Transect_ID']==tid and r['Valid']=='True' for r in reviewed)
    coverage.append({'Transect_ID':tid,'Year':2024,'Original_Valid_Months':len(b),'Reviewed_Valid_Months':len(a),
        'Original_Month_List':';'.join(b),'Reviewed_Month_List':';'.join(a),
        'Original_Valid_Image_Measurements':original_daily,'Reviewed_Valid_Image_Measurements':reviewed_daily,
        'Minimum_Required_Months':6,'Meets_Six_Months':len(a)>=6})
save_csv(output/'coverage_2024.csv',coverage)
roundtrip=list(csv.DictReader((output/'measurements_reviewed_2024.csv').read_text().splitlines()))
assert roundtrip==reviewed
assert len({(r['Source_File'],r['Transect_ID']) for r in roundtrip})==225
for r in roundtrip:
    if r['Valid']=='True':assert 0<=float(r['Cross_Shore_Distance_m'])<=300.000001
    else:assert r['Cross_Shore_Distance_m']==''
    for key in ['Date','Transect_ID','Satellite','Source_File','Tide_Corrected']:
        assert r[key]==original_by_key[(r['Source_File'],r['Transect_ID'])][key]
recovered=sum(o['Valid']=='False' and n['Valid']=='True' for o,n in zip(original,reviewed))
removed=sum(o['Valid']=='True' and n['Valid']=='False' for o,n in zip(original,reviewed))
adjusted=sum(o['Valid']=='True' and n['Valid']=='True' and abs(float(o['Cross_Shore_Distance_m'])-float(n['Cross_Shore_Distance_m']))>1e-5 for o,n in zip(original,reviewed))
verification=check_sources()
assert hashlib.sha256((output/'measurements_original_2024.csv').read_bytes()).hexdigest()==before[str((work/'2024/measurements.csv').resolve())]
manifest={'site':'roi_c8_jps_082','year':2024,'manual_review':True,'scope':'2024 only; separate copy; not applied to pipeline',
    'source_measurements':str(work/'2024/measurements.csv'),'reviewed_measurements':str(output/'measurements_reviewed_2024.csv'),
    'scenes_with_nonempty_original_shoreline':45,'scenes_with_accepted_measurements':sum(bool(s['valid_transects']) for s in scene_results),
    'scenes_rejected_visually':[s['index'] for s in scene_results if not s['selected_component_ids']],
    'reviewed_rows':225,'recovered_previously_invalid_rows':recovered,'removed_originally_valid_rows':removed,
    'adjusted_originally_valid_positions':adjusted,'intersection_qc_unchanged':qc,
    'extraction_settings_unchanged':{'reference_buffer_m':100,'cloud_threshold':.30,'cloud_distance_m':300,'min_contour_length_m':200,
        'nodata_distance_m':30,'s2cloudless_probability':40,'min_beach_area_m2':1000,'pan_off':False,
        'mndwi_threshold':'original saved per image; no retuning','transect_chainage_bounds':'0 to original endpoint length'},
    'selection_method':'Whole original surviving contour components selected visually. No point deletion within selected components, contour extensions, buffer widening, QC relaxation, interpolation, or retraining.',
    'all_five_meet_six_months_2024':all(r['Meets_Six_Months'] for r in coverage),'coverage':coverage,
    'source_integrity':verification,'scenes':scene_results,
    'review_data_sha256':hashlib.sha256((output/'measurements_reviewed_2024.csv').read_bytes()).hexdigest(),
    'visual_decisions_sha256':hashlib.sha256((output/'visual_decisions.json').read_bytes()).hexdigest()}
(output/'review_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
print('REVIEW COMPLETE',json.dumps({k:manifest[k] for k in ['scenes_with_accepted_measurements','reviewed_rows','recovered_previously_invalid_rows','removed_originally_valid_rows','adjusted_originally_valid_positions','all_five_meet_six_months_2024']}),flush=True)
for row in coverage:print('COVERAGE',json.dumps(row),flush=True)
print('SOURCE INTEGRITY',json.dumps(verification),flush=True)

