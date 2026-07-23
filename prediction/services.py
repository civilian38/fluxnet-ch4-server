import os
import cdsapi
import xarray as xr
import pandas as pd
import numpy as np
import zipfile
import glob
import ee
from tqdm.auto import tqdm
import datetime
import shutil
import json
from google.oauth2 import service_account

from django.db import transaction
from .models import Location, WeeklyEnvironmentData

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

    try:
        with transaction.atomic():
            for _, row in df_weekly.iterrows():
                WeeklyEnvironmentData.objects.update_or_create(
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
        print("\n최종 전처리 및 DB 저장 완료.")

    finally:
        # 임시 디렉토리 정리 (shutil 사용)
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            print(f"\n임시 디렉토리 정리 완료: {TEMP_DIR}")