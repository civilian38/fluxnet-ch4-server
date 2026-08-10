import os
import cdsapi
import xarray as xr
import pandas as pd
import numpy as np
import zipfile
import random
import glob
import ee
from tqdm.auto import tqdm
import datetime
from datetime import timedelta
import shutil
import json
from google.oauth2 import service_account

from django.db import transaction
from .models import Location, WeeklyEnvironmentData, CH4PredictionValue
from django.apps import apps

def preprocess(target_date: datetime.date):
    tqdm.pandas()

    # ============================================================================
    # 1. 기준 날짜 설정 및 7일 기간 계산
    # ============================================================================
    start_date = target_date - datetime.timedelta(days=6)
    cds_date_range = f"{start_date.strftime('%Y-%m-%d')}/{target_date.strftime('%Y-%m-%d')}"
    print(f"분석 대상 기간: {start_date} ~ {target_date}")

    # ============================================================================
    # 2. 컨테이너 환경 변수 및 임시 디렉토리 설정 (ACA 환경)
    # ============================================================================
    TEMP_DIR = os.getenv('TEMP_DIR', '/tmp/era5_processing')
    os.makedirs(TEMP_DIR, exist_ok=True)

    # ============================================================================
    # 3. 타겟 좌표 로드 및 다운로드
    # ============================================================================
    # DB에서 Location 객체를 모두 가져와 id, 위도, 경도를 DataFrame으로 구성합니다.
    locations = Location.objects.all()
    target_data = [
        {'location_id': loc.id, 'latitude': loc.point.y, 'longitude': loc.point.x}
        for loc in locations
    ]
    target_df = pd.DataFrame(target_data)

    print(f"총 {len(target_data)}개의 좌표에 대해 ERA5 데이터를 다운로드합니다...")
    CDSAPI_URL = os.getenv('CDSAPI_URL', 'https://cds.climate.copernicus.eu/api')
    CDSAPI_KEY = os.getenv('CDSAPI_KEY')
    c = cdsapi.Client(url=CDSAPI_URL, key=CDSAPI_KEY)

    downloaded_files = []
    buffer = 0.15

    for i, row in target_df.iterrows():
        loc_id = row['location_id']  # location_id 추출
        lat = row['latitude']
        lon = row['longitude']
        bbox = [lat + buffer, lon - buffer, lat - buffer, lon + buffer]
        file_path = os.path.join(TEMP_DIR, f'era5_raw_{i}.zip')

        print(f"[{i + 1}/{len(target_data)}] 다운로드 중... (좌표: {lat}, {lon})")
        try:
            c.retrieve(
                'reanalysis-era5-single-levels',
                {
                    'product_type': 'reanalysis',
                    'format': 'netcdf',
                    'variable': [
                        '10m_u_component_of_wind', '10m_v_component_of_wind',
                        '2m_dewpoint_temperature', '2m_temperature',
                        'skin_temperature', 'soil_temperature_level_1',
                        'surface_net_solar_radiation', 'surface_net_thermal_radiation',
                        'surface_pressure', 'surface_sensible_heat_flux',
                        'total_precipitation',
                    ],
                    'date': cds_date_range,
                    'time': [f"{str(h).zfill(2)}:00" for h in range(24)],
                    'area': bbox,
                },
                file_path
            )
            downloaded_files.append({
                'location_id': loc_id,
                'file_path': file_path
            })
        except Exception as e:
            print(f"다운로드 실패 (좌표: {lat}, {lon}): {e}")

    # ============================================================================
    # 4. 데이터 병합 및 7일 평균 단일 그룹화
    # ============================================================================
    print("\n데이터를 병합하고 7일 평균을 계산합니다...")
    df_list = []
    target_cols = ['u10', 'v10', 'd2m', 't2m', 'skt', 'stl1', 'ssr', 'str', 'sp', 'sshf', 'tp']

    for i, file_info in enumerate(downloaded_files):
        loc_id = file_info['location_id']
        file_path = file_info['file_path']

        try:
            extract_dir = os.path.join(TEMP_DIR, f'extracted_{i}')
            os.makedirs(extract_dir, exist_ok=True)
            nc_files_to_process = []

            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                nc_files_to_process = glob.glob(os.path.join(extract_dir, '*.nc'))
            else:
                nc_files_to_process = [file_path]

            datasets = [xr.open_dataset(nc, engine='netcdf4') for nc in nc_files_to_process]
            ds_combined = xr.merge(datasets, compat='override')

            if 'expver' in ds_combined.dims:
                ds_combined = ds_combined.mean(dim='expver', skipna=True)

            time_dim = 'valid_time' if 'valid_time' in ds_combined.dims else 'time'

            ds_daily = ds_combined.resample({time_dim: '1D'}).mean()
            df = ds_daily.to_dataframe().reset_index()

            if time_dim == 'time' and 'time' in df.columns:
                df = df.rename(columns={'time': 'valid_time'})

            df['location_id'] = loc_id

            df_list.append(df)

            ds_combined.close()
            for ds in datasets:
                ds.close()

            for nc_file in nc_files_to_process:
                if nc_file != file_path and os.path.exists(nc_file):
                    os.remove(nc_file)

            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(extract_dir) and not os.listdir(extract_dir):
                os.rmdir(extract_dir)

        except Exception as e:
            print(f"파일 처리 실패 ({file_path}): {e}")

    # 리스트에 모인 DataFrame 하나로 합치기
    df_era5_all = pd.concat(df_list, ignore_index=True)

    df_era5_all = df_era5_all.groupby(['location_id', 'valid_time'])[target_cols].mean().reset_index()
    df_era5_final = pd.merge(df_era5_all, target_df, on='location_id')

    # 7일 치 데이터를 하나의 평균값으로 압축
    df_weekly = df_era5_final.groupby(['location_id', 'latitude', 'longitude'])[target_cols].mean().reset_index()

    # 시작일과 종료일 컬럼을 수동으로 삽입
    df_weekly['TIMESTAMP_START'] = pd.to_datetime(start_date)
    df_weekly['TIMESTAMP_END'] = pd.to_datetime(target_date)

    cols_ordered = ['location_id', 'TIMESTAMP_START', 'TIMESTAMP_END', 'latitude', 'longitude'] + target_cols
    df_weekly = df_weekly[cols_ordered]

    # ============================================================================
    # 5. GEE 기반 Sentinel-1 위성 데이터 추출
    # ============================================================================
    print("\nGoogle Earth Engine 데이터를 추출합니다...")

    gee_json_string = os.getenv('GEE_JSON_KEY_STRING')
    gee_project_id = os.getenv('GEE_PROJECT_ID', 'YOUR_PROJECT_ID')

    try:
        if gee_json_string:
            # 1. 환경 변수에서 JSON을 읽어 딕셔너리로 변환
            key_dict = json.loads(gee_json_string)

            # 2. 기본 자격 증명 생성
            base_credentials = service_account.Credentials.from_service_account_info(key_dict)

            # 3. ★ 핵심: Earth Engine 및 Cloud Platform 접근 권한(Scope) 추가 ★
            scopes = [
                'https://www.googleapis.com/auth/earthengine',
                'https://www.googleapis.com/auth/cloud-platform'
            ]
            credentials = base_credentials.with_scopes(scopes)

            # 4. 권한이 추가된 객체로 GEE 초기화
            ee.Initialize(credentials, project=gee_project_id)
            print("GEE 인증 및 초기화 성공!")

        else:
            # 로컬 테스트용 등 자격 증명이 없을 때의 대비
            ee.Initialize(project=gee_project_id)
            print("기본 자격 증명으로 GEE 초기화 성공!")

    except Exception as e:
        print(f"GEE 인증 실패: {e}")
        raise e

    def get_s1_stats(row):
        try:
            point = ee.Geometry.Point([row['longitude'], row['latitude']])

            s1_col = ee.ImageCollection('COPERNICUS/S1_GRD') \
                .filterBounds(point) \
                .filterDate(ee.Date(start_date.strftime('%Y-%m-%d')),
                            ee.Date(target_date.strftime('%Y-%m-%d')).advance(1, 'day')) \
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
                .filter(ee.Filter.eq('instrumentMode', 'IW'))

            if s1_col.size().getInfo() == 0:
                return pd.Series([np.nan, np.nan, np.nan])

            mean_img = s1_col.mean()
            vv = mean_img.select('VV')
            vh = mean_img.select('VH')
            sdwi = vv.multiply(vh).multiply(10).log().subtract(8).rename('SDWI')

            stats = mean_img.addBands(sdwi).reduceRegion(
                reducer=ee.Reducer.mean(), geometry=point, scale=10
            ).getInfo()

            return pd.Series([stats.get('VV'), stats.get('VH'), stats.get('SDWI')])
        except Exception:
            return pd.Series([np.nan, np.nan, np.nan])

    # 위성 데이터 추출
    df_weekly[['VV', 'VH', 'SDWI']] = df_weekly.progress_apply(get_s1_stats, axis=1)

    # 결측치(NaN)가 하나라도 있는 행은 완전히 삭제
    df_weekly = df_weekly.dropna(subset=['VV', 'VH', 'SDWI']).reset_index(drop=True)

    # ============================================================================
    # 6. 기상 변수 최종 변환
    # ============================================================================
    print("\n기상 변수를 변환합니다...")
    seconds_in_1day = 24 * 3600

    df_weekly['WS'] = (df_weekly['u10'] ** 2 + df_weekly['v10'] ** 2) ** 0.5
    df_weekly['TS_1'] = df_weekly['skt'] - 273.15
    df_weekly['TS_2'] = df_weekly['stl1'] - 273.15
    df_weekly['G'] = df_weekly['sshf'] / seconds_in_1day
    df_weekly['PA'] = df_weekly['sp'] / 1000
    df_weekly['P'] = df_weekly['tp'] * 1000

    TA_celsius = df_weekly['t2m'] - 273.15
    d2m_celsius = df_weekly['d2m'] - 273.15

    e_s_kpa = 0.61078 * np.exp((17.27 * TA_celsius) / (TA_celsius + 237.3))
    e_a_kpa = 0.61078 * np.exp((17.27 * d2m_celsius) / (d2m_celsius + 237.3))
    df_weekly['VPD'] = (e_s_kpa - e_a_kpa) * 10

    ssr_wm2 = df_weekly['ssr'] / seconds_in_1day
    str_wm2 = df_weekly['str'] / seconds_in_1day
    df_weekly['NETRAD'] = (abs(ssr_wm2) + abs(str_wm2)) * 24
    df_weekly['TA'] = TA_celsius + 273.15

    # ============================================================================
    # 7. Django 데이터베이스(WeeklyEnvironmentData)에 저장
    # ============================================================================
    print("\n데이터베이스에 결과를 저장합니다...")
    
    # 결과를 담을 리스트 초기화
    processed_objects = [] 

    try:
        with transaction.atomic():
            for _, row in df_weekly.iterrows():
                obj, created = WeeklyEnvironmentData.objects.update_or_create(
                    location_id=row['location_id'],
                    start_date=row['TIMESTAMP_START'].date(),
                    defaults={
                        'end_date': row['TIMESTAMP_END'].date(),
                        'ws': row['WS'],
                        'ta': row['TA'],
                        'ts_1': row['TS_1'],
                        'ts_2': row['TS_2'],
                        'g': row['G'],
                        'pa': row['PA'],
                        'p': row['P'],
                        'vpd': row['VPD'],
                        'netrad': row['NETRAD'],
                        'vv': row['VV'],
                        'vh': row['VH'],
                        'sdwi': row['SDWI'],
                    }
                )
                
                processed_objects.append(obj)

        print(f"\n최종 전처리 및 DB 저장 완료. (총 {len(processed_objects)}개 저장)")

    finally:
        # 임시 디렉토리 정리 (shutil 사용)
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            print(f"\n임시 디렉토리 정리 완료: {TEMP_DIR}")

    return processed_objects

def predict_ch4_for_instance(env_data_instance: WeeklyEnvironmentData):
    # 1. Django에 등록된 앱 인스턴스를 가져옵니다. 
    app_config = apps.get_app_config('prediction') 
    
    # 2. 해당 인스턴스에 로드된 모델을 꺼냅니다.
    model = app_config.ml_model

    if model is None:
        raise ValueError("모델이 로드되지 않았습니다.")
    # 2. 모델이 기대하는 피처 순서 확인
    feature_cols = list(model.feature_names_in_)

    # 3. Django DB 인스턴스의 데이터를 딕셔너리로 매핑 
    data_dict = {'NETRAD': env_data_instance.netrad,
        'WS': env_data_instance.ws,
        'G': env_data_instance.g,
        'PA': env_data_instance.pa,
        'TA': env_data_instance.ta,
        'VPD': env_data_instance.vpd,
        'P': env_data_instance.p,
        'TS_1': env_data_instance.ts_1,
        'TS_2': env_data_instance.ts_2,
        'VV': env_data_instance.vv,
        'VH': env_data_instance.vh,
        'SDWI': env_data_instance.sdwi,
    }

    # 4. DataFrame 생성 및 피처 순서 강제 정렬
    df = pd.DataFrame([data_dict])
    X = df[feature_cols] # 순서 보장

    # 5. 예측
    pred_value = model.predict(X)
    
    return pred_value[0] # 단일 값이므로 첫 번째 요소 반환

def update_ch4_for_locations(date: datetime.date):
    # 1. 환경 데이터 전처리 및 인스턴스 획득
    env_data = preprocess(date)
    
    if not env_data:
        print("전처리된 환경 데이터가 없습니다.")
        return

    # 2. 모델 로드 (반복문 밖에서 한 번만 실행)
    app_config = apps.get_app_config('prediction') 
    model = app_config.ml_model

    if model is None:
        raise ValueError("모델이 로드되지 않았습니다.")
        
    feature_cols = list(model.feature_names_in_)

    # 3. 모델 예측을 위한 데이터프레임 일괄(Batch) 구성
    data_dicts = []
    for instance in env_data:
        data_dicts.append({
            'env_data_id': instance.id,  # 나중에 매핑하기 위한 키
            'NETRAD': instance.netrad,
            'WS': instance.ws,
            'G': instance.g,
            'PA': instance.pa,
            'TA': instance.ta,
            'VPD': instance.vpd,
            'P': instance.p,
            'TS_1': instance.ts_1,
            'TS_2': instance.ts_2,
            'VV': instance.vv,
            'VH': instance.vh,
            'SDWI': instance.sdwi,
        })

    df = pd.DataFrame(data_dicts)
    X = df[feature_cols]  # 모델이 학습될 때와 동일한 컬럼 순서 보장

    # 4. 일괄 예측 (단 한 번의 predict 호출로 속도 극대화)
    print("메탄(CH4) 발생량을 예측합니다...")
    predictions = model.predict(X)
    
    # 예측된 값을 DataFrame에 추가
    df['predicted_value'] = predictions

    # 5. DB 일괄 저장을 위한 객체 리스트 생성
    ch4_objects = []
    for _, row in df.iterrows():
        ch4_objects.append(
            CH4PredictionValue(
                env_data_id=int(row['env_data_id']),
                value=row['predicted_value']
            )
        )

    # 6. 데이터베이스 일괄 저장 및 업데이트
    print("예측 결과를 데이터베이스에 저장합니다...")
    CH4PredictionValue.objects.bulk_create(
        ch4_objects,
        update_conflicts=True,
        unique_fields=['env_data'],
        update_fields=['value']
    )
    
    print(f"총 {len(ch4_objects)}개의 CH4 예측값이 업데이트/생성 되었습니다.")

def inject_bulk_data():
    test_location = Location.objects.get(id=4)
    
    # 1. 기준이 되는 현재 데이터 가져오기 
    # 모델의 ordering=['-start_date'] 속성 덕분에 first()로 가장 최근 데이터를 가져옵니다.
    current_env = test_location.weekly_data.first()
    
    if not current_env:
        print("기준이 되는 WeeklyEnvironmentData가 존재하지 않습니다.")
        return
        
    try:
        current_ch4 = current_env.prediction_value
    except CH4PredictionValue.DoesNotExist:
        print("기준이 되는 CH4PredictionValue가 존재하지 않습니다.")
        return

    # 노이즈(변화량)를 추가하는 헬퍼 함수
    def get_varied_value(value, variation_range=1.0, min_zero=False):
        new_value = value + random.uniform(-variation_range, variation_range)
        if min_zero:
            return round(max(0.0, new_value), 3)
        return round(new_value, 3)

    # 루프 안에서 이전 상태를 추적하기 위한 변수
    prev_env = current_env
    prev_ch4_val = current_ch4.value

    # 30개의 생성 쿼리가 발생하므로 하나의 트랜잭션으로 묶어 처리 속도 향상
    with transaction.atomic():
        for _ in range(30):
            # 2. 날짜는 1주일(7일) 이전으로 설정
            new_start_date = prev_env.start_date - timedelta(days=7)
            new_end_date = prev_env.end_date - timedelta(days=7)
            
            # 각 필드에 랜덤한 숫자 더하거나 빼기 (데이터 특성에 따라 변화 폭 지정)
            new_env = WeeklyEnvironmentData.objects.create(
                location=test_location,
                start_date=new_start_date,
                end_date=new_end_date,
                
                ws=get_varied_value(prev_env.ws, 0.5, min_zero=True),  # 풍속 (0 이상)
                ta=get_varied_value(prev_env.ta, 2.0),
                ts_1=get_varied_value(prev_env.ts_1, 2.0),
                ts_2=get_varied_value(prev_env.ts_2, 2.0),
                g=get_varied_value(prev_env.g, 5.0),
                pa=get_varied_value(prev_env.pa, 0.5),
                p=get_varied_value(prev_env.p, 5.0, min_zero=True),    # 강수량 (0 이상)
                vpd=get_varied_value(prev_env.vpd, 0.5),
                netrad=get_varied_value(prev_env.netrad, 10.0),
                vv=get_varied_value(prev_env.vv, 1.0),
                vh=get_varied_value(prev_env.vh, 1.0),
                sdwi=get_varied_value(prev_env.sdwi, 0.05)             # 수분 지수
            )
            
            # 새로운 CH4 예측값 생성 및 연결
            new_ch4_val = get_varied_value(prev_ch4_val, 1.5)
            CH4PredictionValue.objects.create(
                env_data=new_env,
                value=new_ch4_val
            )
            
            # 다음 반복을 위해 기준 값을 방금 생성한 객체로 업데이트
            prev_env = new_env

    print("30개의 과거 테스트 데이터가 성공적으로 생성되었습니다.")