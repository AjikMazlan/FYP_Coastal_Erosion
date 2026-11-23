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
review_root=root/'results/coastsat_reviews/roi_c8_jps_082_contour_review'
year=sys.argv[1]
assert year in {'2020','2021','2022','2023','2025'}
output=review_root/year
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

import matplotlib.pyplot as plt
from PIL import Image,ImageDraw
work=root/'results/shoreline_pipeline/monthly_v1/roi_c8_jps_082'
protocol=json.loads(read_protected(work/'protocol.json'));site=protocol['site'];qc=protocol['intersection_qc']
reference_path=root/site['reference'];transects_path=root/site['transects']
features=json.loads(read_protected(transects_path))['features']
transects={str(f['properties']['name']):np.asarray(f['geometry']['coordinates'],dtype=float) for f in features}
reference=np.asarray(json.loads(read_protected(reference_path))['features'][0]['geometry']['coordinates'])
cum=np.r_[0,np.cumsum(np.linalg.norm(np.diff(reference,axis=0),axis=1))]
samples=np.r_[np.arange(0,cum[-1],1),cum[-1]]
reference=np.column_stack([np.interp(samples,cum,reference[:,i]) for i in (0,1)])
settings={'reference_shoreline':reference,'max_dist_ref':100,'output_epsg':32648}
original=read_protected(work/f'{year}/measurements.csv')
rows=list(csv.DictReader(original.decode('utf-8-sig').splitlines()))
by_key={(r['Source_File'],r['Transect_ID']):r for r in rows}
read_protected(root/site['base_config'])
read_protected(root/'configs/coastsat/shoreline_batch.json')
folder=coast/'data'/site['existing_inputs'].get(year,site['input_prefix']+'_'+year)
raw=pickle.loads(read_protected(folder/f'{folder.name}_output.pkl'))
metadata=pickle.loads(read_protected(folder/f'{folder.name}_metadata.pkl'))
marker=json.loads(read_protected(work/f'{year}/extraction_complete.json'))
assert hashes[str((folder/f'{folder.name}_output.pkl').resolve())]==marker['output_sha256']
(output/'source_hashes_before.json').write_text(json.dumps(hashes,indent=2)+'\n')
flat=np.vstack(list(transects.values()));low=flat.min(axis=0)-90;high=flat.max(axis=0)+90
center=(low+high)/2;span=max(high-low)
bbox=[center[0]-span/2,center[0]+span/2,center[1]-span/2,center[1]+span/2]
palette=['#ffde00','#00e5ff','#ff6600','#00ff66','#ff334d','#aa77ff','#ffffff','#ff88cc','#0099ff','#99cc00']
all_scenes=[]
for ri in sorted(range(len(raw['filename'])),key=lambda i:raw['filename'][i]):
    if not len(raw['shorelines'][ri]):continue
    name=raw['filename'][ri];sat=raw['satname'][ri];meta=metadata[sat];mi=meta['filenames'].index(name)
    epsg=int(meta['epsg'][mi]);assert epsg==32648
    files=SDS_tools.get_filenames(name,SDS_tools.get_filepath({'filepath':str(coast/'data'),'sitename':folder.name},sat),sat)
    im,geo,cloud,_,_,nodata=SDS_preprocess.preprocess_single(files,sat,False,False,40)
    cloud_only=np.logical_xor(cloud,nodata)
    cloud_fraction=float(cloud_only.sum()/(~nodata).sum())
    assert cloud.mean()<=.99 and cloud_fraction<=.30
    threshold=float(raw['MNDWI_threshold'][ri])
    buf=SDS_shoreline.create_shoreline_buffer(cloud.shape,geo,epsg,15 if sat=='L8' else 10,settings)
    nd=SDS_tools.nd_index(im[:,:,4],im[:,:,1],cloud);nd[~buf]=np.nan
    contours=SDS_shoreline.process_contours(find_contours(nd,threshold))
    world=SDS_tools.convert_epsg(SDS_tools.convert_pix2world(contours,geo),epsg,32648)
    components=[];final_all=[]
    for ci,p in enumerate(world):
        length=float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum())
        if length<200:continue
        clear=filter_mask(p,cloud_only,geo,epsg,300)
        final=filter_mask(clear,nodata,geo,epsg,30)
        if not len(final):continue
        final_all.append(final)
        values={tid:stats(final,t,qc) for tid,t in transects.items()}
        official=SDS_transects.compute_intersection_QC({'shorelines':[final]},transects,qc)
        for tid,v in values.items():
            assert v['valid']==bool(np.isfinite(official[tid][0]) and 0<=official[tid][0]<=np.linalg.norm(transects[tid][1]-transects[tid][0]))
            if v['valid']:assert np.isclose(v['median'],official[tid][0])
        components.append({'id':ci,'length_before_cloud_m':length,'points':final.tolist(),'qc':values})
    merged=np.vstack(final_all) if final_all else empty
    assert merged.shape==raw['shorelines'][ri].shape,(name,merged.shape,raw['shorelines'][ri].shape)
    assert np.allclose(merged,raw['shorelines'][ri],rtol=0,atol=1e-7),name
    original_qc={tid:stats(merged,t,qc) for tid,t in transects.items()}
    for tid,v in original_qc.items():assert v['valid']==(by_key[(name,tid)]['Valid']=='True')
    index=len(all_scenes)+1
    rec={'index':index,'filename':name,'image_path':str(files[0]),'date':str(raw['dates'][ri])[:10],'satellite':sat,'cloud_fraction':cloud_fraction,
         'combined_mask_fraction':float(cloud.mean()),'mndwi_threshold':threshold,'original_qc':original_qc,'components':components}
    rgb=SDS_preprocess.rescale_image_intensity(im[:,:,[2,1,0]],cloud,99.9)
    fig,ax=plt.subplots(figsize=(5,5))
    ax.imshow(rgb,extent=[geo[0],geo[0]+geo[1]*im.shape[1],geo[3]+geo[5]*im.shape[0],geo[3]],origin='upper')
    ax.plot(reference[:,0],reference[:,1],color='white',lw=.8,ls='--',alpha=.7)
    for tid,t in transects.items():
        ax.plot(t[:,0],t[:,1],color='magenta',lw=1)
        ax.text(t[0,0]-8,t[0,1]-8,'T'+tid,fontsize=7,color='white',ha='right',bbox=dict(facecolor='black',alpha=.65,pad=1))
    for c in components:
        p=np.asarray(c['points']);visible=(p[:,0]>=bbox[0])&(p[:,0]<=bbox[1])&(p[:,1]>=bbox[2])&(p[:,1]<=bbox[3])
        colour=palette[c['id']%len(palette)]
        # Show points and only short edges, preserving gaps removed by cloud/nodata.
        if len(p)>1:
            for run in np.split(np.arange(len(p)),np.where(np.linalg.norm(np.diff(p,axis=0),axis=1)>35)[0]+1):
                ax.plot(p[run,0],p[run,1],color=colour,lw=1.2)
        if visible.any():
            q=p[visible];anchor=q[len(q)//2]
            ax.text(anchor[0]+5,anchor[1]+8,'C'+str(c['id']),fontsize=8,color=colour,bbox=dict(facecolor='black',alpha=.8,pad=2))
    ax.set_xlim(bbox[:2]);ax.set_ylim(bbox[2:]);ax.set_xticks([]);ax.set_yticks([])
    ax.set_title(f"#{index:02d} {name[:19]} {sat} {name.split('_')[2]}\nCloud {cloud_fraction:.1%}; component IDs Cn",fontsize=8)
    fig.tight_layout(pad=.25)
    image_path=output/f'scene_{index:02d}.png';fig.savefig(image_path,dpi=90);plt.close(fig)
    rec['review_image']=str(image_path.relative_to(root))
    all_scenes.append(rec)
    print(f"PREPARED {index:02d}: {name}; components {[c['id'] for c in components]}",flush=True)
(output/'scenes.json').write_text(json.dumps(all_scenes,indent=2,allow_nan=False)+'\n')
assert len(all_scenes)*len(transects)==len(rows)
for start in range(0,len(all_scenes),12):
    canvas=Image.new('RGB',(1440,1080),'white')
    for j,scene in enumerate(all_scenes[start:start+12]):
        pic=Image.open(root/scene['review_image']).convert('RGB');pic.thumbnail((360,360),Image.Resampling.LANCZOS)
        canvas.paste(pic,((j%4)*360,(j//4)*360))
    canvas.save(output/f'contact_sheet_{start//12+1:02d}.png')
print('PREPARE COMPLETE',len(all_scenes),flush=True)
