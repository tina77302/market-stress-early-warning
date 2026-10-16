"""No network, no production data/model writes."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import sqlite3
import pandas as pd
import pytest
from src.korea.ingestion import runtime_end, resume_date, atomic_csv, receipt
from src.korea.shadow_pipeline import align_sources, common_path, append_forecast, SERIES


def test_dynamic_end_and_holidays():
    now = datetime(2026,10,16,10,tzinfo=ZoneInfo('Asia/Seoul'))
    assert runtime_end(now=now).date().isoformat() == '2026-10-15'
    assert runtime_end(now=datetime(2026,10,17,12,tzinfo=now.tzinfo)).date().isoformat() == '2026-10-16'
    assert runtime_end(now=datetime(2026,10,9,18,tzinfo=now.tzinfo)).date().isoformat() == '2026-10-08'
    assert runtime_end('20261002', now=now).date().isoformat() == '2026-10-02'
    with pytest.raises(ValueError):runtime_end('20261019',now=now)


def test_resume_retries_holes():
    start,end=pd.Timestamp('2026-10-12').to_pydatetime(),pd.Timestamp('2026-10-15').to_pydatetime()
    assert resume_date(['2026-10-12','2026-10-14','2026-10-15'],start,end).day==13
    assert resume_date(pd.date_range(start,end),start,end).day==16


def sources():
    axis = pd.to_datetime(['2026-10-12','2026-10-13','2026-10-14','2026-10-15'])
    return {name:pd.DataFrame({'Date':axis,'value':[1.,2.,3.,4.],
                              'retrieved_at':'2026-10-16T00:00:00Z'}) for name in SERIES}


@pytest.mark.parametrize('lagging',SERIES[2:])
def test_individual_credit_leg_one_day_lag(lagging):
    s=sources();s[lagging]=s[lagging].iloc[:-1]
    exact,metadata=align_sources(s,'2026-10-16T01:00:00Z')
    common,origin=common_path(exact)
    assert origin==pd.Timestamp('2026-10-14')
    result,metadata=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    assert result.index[-1]==pd.Timestamp('2026-10-15')
    m=metadata.loc[metadata.Date.eq('2026-10-15')&metadata.series.eq(lagging)].iloc[0]
    assert m.used_observation_date==pd.Timestamp('2026-10-14')
    assert m.staleness_trading_days==1 and m.is_stale and m.accepted
    assert m.fill_method=='BACKWARD_ASOF' and pd.isna(m.source_available_at)
    assert result.iloc[-1].Korea_Credit_Spread == (3-4 if lagging==SERIES[3] else 4-3)


def test_old_credit_rejected_and_no_forward_look():
    s=sources();s[SERIES[3]]=s[SERIES[3]].iloc[:1]
    result,m=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    assert pd.isna(result.iloc[-1][SERIES[3]])
    s=sources();s[SERIES[3]]=s[SERIES[3]].iloc[2:]
    result,m=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    assert result.iloc[:2][SERIES[3]].isna().all()
    assert (m.used_observation_date.dropna()<=m.loc[m.used_observation_date.notna(),'Date']).all()


def test_cutoff_and_unknown_availability_fail_closed():
    s=sources();s['VKOSPI']['source_available_at']='2026-10-17T00:00:00Z'
    result,_=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    assert result.VKOSPI.isna().all()
    s=sources();s['VKOSPI']['retrieved_at']=None
    result,m=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    assert result.VKOSPI.isna().all()
    result,m=align_sources(s,'2026-10-16T01:00:00Z',asof=True,allow_proxy=True)
    assert result.VKOSPI.notna().all()
    assert m.loc[m.series.eq('VKOSPI'),'availability_evidence'].eq('OBSERVATION_DATE_PROXY').all()
    result,_=align_sources(s,'2026-10-15T12:00:00Z',asof=True)
    assert result.empty  # all equity receipts arrived after this cutoff


def record():
    return dict(market='korea',information_cutoff='2026-10-16T01:00:00Z',model_sha256='a'*64,
                feature_schema_version='frozen-korea-17',forecast_origin_session='2026-10-15',
                input_sha256='b'*64,path='experimental_asof',prediction_timestamp='2026-10-16T01:01:00Z',
                v1_risk_score=32.3,current_stress=.720,shadow_outputs={'10D':32.3},warning_state='BELOW_V1_WARNING')


def test_immutable_append_retry_and_next_cutoff(tmp_path):
    path=tmp_path/'history.sqlite3';r=record();first,new=append_forecast(path,r);assert new
    r['prediction_timestamp']='2026-10-16T01:02:00Z'
    second,new=append_forecast(path,r);assert second==first and not new
    r['information_cutoff']='2026-10-16T02:00:00Z';r['prediction_timestamp']='2026-10-16T02:01:00Z';third,new=append_forecast(path,r)
    assert third!=first and new
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM forecasts').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==3
        original=json.loads(db.execute('SELECT payload FROM forecasts WHERE forecast_id=?',(first,)).fetchone()[0])
        assert original['prediction_timestamp']=='2026-10-16T01:01:00Z'
        with pytest.raises(sqlite3.IntegrityError):db.execute('UPDATE forecasts SET payload=?',('{}',))
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM forecasts')
    r=record();r['v1_risk_score']=90
    with pytest.raises(ValueError):append_forecast(path,r)


def test_atomic_csv_and_receipt(tmp_path):
    p=tmp_path/'raw.csv';d=pd.DataFrame({'Date':['2026-10-15'],'value':[3.]})
    atomic_csv(d,p);receipt(p,'example',d)
    r=json.loads(next((tmp_path/'receipts').glob('*.json')).read_text())
    assert r['source_available_at'] is None and r['retrieved_at']
    assert pd.read_csv(p).value.iloc[0]==3
    assert not list(tmp_path.glob('*.tmp'))


def test_calendar_age_limit_across_holiday():
    s={name:pd.DataFrame({'Date':pd.to_datetime(['2026-10-02','2026-10-06']),
                         'value':[1.,2.],'retrieved_at':'2026-10-07T00:00:00Z'}) for name in SERIES}
    s[SERIES[3]]=s[SERIES[3]].iloc[:1]
    frame,m=align_sources(s,'2026-10-07T01:00:00Z',asof=True)
    row=m.loc[m.Date.eq('2026-10-06')&m.series.eq(SERIES[3])].iloc[0]
    assert row.staleness_trading_days==1 and row.staleness_calendar_days==4 and row.accepted
    frame,m=align_sources(s,'2026-10-07T01:00:00Z',asof=True,max_calendar_days=3)
    assert pd.isna(frame.iloc[-1][SERIES[3]])


def test_empty_ecos_response_preserves_existing_file(tmp_path,monkeypatch):
    import importlib
    from types import SimpleNamespace
    monkeypatch.setenv('ECOS_API_KEY','unit-test-placeholder')
    module=importlib.import_module('src.korea.download_ecos_credit')
    raw=tmp_path/'raw';raw.mkdir();p=raw/'ecos_credit.csv';p.write_text('unchanged existing data')
    monkeypatch.setattr(module,'configure',lambda:SimpleNamespace(start=pd.Timestamp('2026-10-12'),end=pd.Timestamp('2026-10-15'),raw=raw))
    monkeypatch.setattr(module,'fetch_series',lambda name,code:pd.DataFrame({'Date':pd.Series(dtype='datetime64[ns]'),name:pd.Series(dtype=float)}))
    module.main()
    assert p.read_text()=='unchanged existing data'


def test_future_provider_rows_are_not_saved(tmp_path,monkeypatch):
    import importlib
    from types import SimpleNamespace
    monkeypatch.setenv('KRX_API_KEY','unit-test-placeholder')
    m=importlib.import_module('src.korea.download_vkospi')
    raw=tmp_path/'raw';raw.mkdir()
    monkeypatch.setattr(m,'configure',lambda:SimpleNamespace(start=pd.Timestamp('2026-10-14').to_pydatetime(),end=pd.Timestamp('2026-10-15').to_pydatetime(),raw=raw))
    pd.DataFrame({'Date':['2026-10-14'],'Close':[44.91]}).to_csv(raw/'vkospi.csv',index=False)
    monkeypatch.setattr(m,'fetch_krx_date',lambda date:[{'IDX_NM':m.TARGET_INDEX,'BAS_DD':'20261016','CLSPRC_IDX':'50'}])
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    m.main()
    assert pd.read_csv(raw/'vkospi.csv').Date.tolist()==['2026-10-14']


def test_receipt_value_match_does_not_backdate_unrelated_rows(tmp_path):
    from src.korea.shadow_pipeline import load_sources
    pd.DataFrame({'Date':['2026-10-14','2026-10-15'],'Index':['KOSPI200']*2,'Close':[936.82,860.70]}).to_csv(tmp_path/'krx_indices.csv',index=False)
    pd.DataFrame({'Date':['2026-10-14','2026-10-15'],'Close':[44.91,55.38]}).to_csv(tmp_path/'vkospi.csv',index=False)
    pd.DataFrame({'Date':['2026-10-14','2026-10-15'],'Korea_Treasury_3Y':[3.883,3.867],'Korea_Corporate_AAminus_3Y':[4.556,4.546]}).to_csv(tmp_path/'ecos_credit.csv',index=False)
    receipt(tmp_path/'vkospi.csv','VKOSPI',pd.DataFrame({'Date':['2026-10-15'],'Close':[55.38]}))
    s=load_sources(tmp_path)
    assert pd.isna(s['VKOSPI'].retrieved_at.iloc[0])
    assert pd.notna(s['VKOSPI'].retrieved_at.iloc[1])


def test_stale_rejection_is_not_reported_as_used():
    from src.korea.shadow_pipeline import quality
    s=sources();s[SERIES[3]]=s[SERIES[3]].iloc[:1]
    _,m=align_sources(s,'2026-10-16T01:00:00Z',asof=True)
    r=m.loc[m.Date.eq('2026-10-15')&m.series.eq(SERIES[3])].iloc[0]
    assert pd.isna(r.used_observation_date)
    assert r.source_observation_date==pd.Timestamp('2026-10-12')
    assert r.fill_method=='REJECTED_STALE'
    assert quality(m,pd.Timestamp('2026-10-15'))['freshness']=='STALE'


def test_partial_checkpoint_is_preserved_for_backfill(tmp_path,monkeypatch):
    import importlib
    monkeypatch.setenv('KRX_API_KEY','unit-test-placeholder')
    m=importlib.import_module('src.korea.download_vkospi')
    p=tmp_path/'vkospi.csv';pd.DataFrame({'Date':['2026-10-14'],'Close':[44.91]}).to_csv(p,index=False)
    monkeypatch.setattr(m,'OUTPUT_PATH',str(p));monkeypatch.setattr(m,'START_DATE',pd.Timestamp('2010-01-04').to_pydatetime())
    frame,start=m.load_existing_data()
    assert len(frame)==1 and start==m.START_DATE
    assert pd.read_csv(p).Close.iloc[0]==44.91


def test_cli_forwards_historical_range_without_network(tmp_path):
    import os,subprocess
    from pathlib import Path
    env_file=tmp_path/'keys.env';env_file.write_text('KRX_API_KEY=fixture\nECOS_API_KEY=fixture\n')
    fake=tmp_path/'python';args_file=tmp_path/'arguments'
    fake.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$*" >> "$ARGUMENTS_FILE"\n')
    fake.chmod(0o700)
    repo=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHON=str(fake),ENV_FILE=str(env_file),ARGUMENTS_FILE=str(args_file))
    subprocess.run(['bash',str(repo/'cli/fetch_korea_data.sh'),'all','--end-date','2026-10-02','--data-root',str(tmp_path/'data')],env=env,capture_output=True,check=True,timeout=20)
    commands=args_file.read_text().splitlines()
    assert len(commands)==3
    assert all('--end-date 2026-10-02 --data-root ' in c for c in commands)


def test_input_artifacts_are_never_replaced(tmp_path):
    from src.korea.shadow_pipeline import archive_inputs
    hashes=archive_inputs(tmp_path/'artifacts',{'inputs.csv':b'original input'})
    assert archive_inputs(tmp_path/'artifacts',{'inputs.csv':b'original input'})==hashes
    with pytest.raises(ValueError):archive_inputs(tmp_path/'artifacts',{'inputs.csv':b'changed input'})
    assert (tmp_path/'artifacts/inputs.csv').read_bytes()==b'original input'
