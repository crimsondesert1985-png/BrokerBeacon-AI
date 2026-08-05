"""Import official public mortgage-broker rosters into BrokerBeacon.

The Missouri Division of Finance publishes a CSV export of its bank and licensee
search. This importer keeps only rows whose Type is exactly Mortgage Broker,
normalizes license identifiers, and writes them to the source-aware warehouse.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import urllib.request
from datetime import datetime

from national_warehouse import create_import_job, create_source, ingest_companies

NOW=lambda: datetime.now().isoformat(timespec='seconds')
MO_EXPORT='https://finance.mo.gov/bank-licensee-search/export?_format=csv&formpos_institutions_and_professional_registration_job_openings_and_job_information=&page='
UA='BrokerBeacon-Ember/3.0 (+official public license roster import)'


def _fetch_csv(url: str = MO_EXPORT) -> str:
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/csv,application/csv,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f'Official roster returned HTTP {response.status}')
        raw=response.read(20_000_000)
    for encoding in ('utf-8-sig','utf-8','latin-1'):
        try: return raw.decode(encoding)
        except UnicodeDecodeError: pass
    return raw.decode('utf-8','ignore')


def _field(row: dict, *names: str) -> str:
    lowered={str(k or '').strip().lower():str(v or '').strip() for k,v in row.items()}
    for name in names:
        value=lowered.get(name.lower())
        if value: return value
    return ''


def _digits(value: str) -> str:
    return re.sub(r'\D+','',value or '')


def _normalize_state(value: str) -> str:
    value=(value or '').strip().upper()
    aliases={'CALIFORNIA':'CA','MISSOURI':'MO','FLORIDA':'FL','OHIO':'OH','TEXAS':'TX','NEW YORK':'NY','NORTH CAROLINA':'NC','SOUTH CAROLINA':'SC','NEW JERSEY':'NJ','PENNSYLVANIA':'PA','MASSACHUSETTS':'MA','VIRGINIA':'VA','WASHINGTON':'WA','ILLINOIS':'IL','MICHIGAN':'MI','MINNESOTA':'MN','KENTUCKY':'KY','TENNESSEE':'TN','GEORGIA':'GA','ARIZONA':'AZ','COLORADO':'CO','UTAH':'UT','MARYLAND':'MD','INDIANA':'IN','WISCONSIN':'WI','OREGON':'OR','NEVADA':'NV','CONNECTICUT':'CT','ALABAMA':'AL','LOUISIANA':'LA','OKLAHOMA':'OK','KANSAS':'KS','ARKANSAS':'AR','IOWA':'IA','IDAHO':'ID','NEBRASKA':'NE','NEW MEXICO':'NM','NEW HAMPSHIRE':'NH','MAINE':'ME','RHODE ISLAND':'RI','VERMONT':'VT','WEST VIRGINIA':'WV','DELAWARE':'DE','MONTANA':'MT','NORTH DAKOTA':'ND','SOUTH DAKOTA':'SD','WYOMING':'WY','ALASKA':'AK','HAWAII':'HI'}
    return aliases.get(value,value[:2] if len(value)==2 else '')


def import_missouri_broker_roster(conn: sqlite3.Connection, target_minimum: int = 500) -> dict:
    source_id=create_source(conn,'Missouri Division of Finance Mortgage Broker Roster','Official regulator CSV','Public regulator license roster; verify current status before outreach',MO_EXPORT)
    job_id=create_import_job(conn,source_id,'')
    text=_fetch_csv()
    reader=csv.DictReader(io.StringIO(text))
    records=[]; seen=set(); rejected=0
    for row in reader:
        kind=_field(row,'Type','License Type','type_name')
        if kind.strip().lower()!='mortgage broker':
            continue
        name=_field(row,'Name','Entity Name','Company Name')
        license_no=_field(row,'License #','License Number','License','Charter#')
        state=_normalize_state(_field(row,'State'))
        city=_field(row,'City')
        postal=_field(row,'Zip','ZIP Code','Postal Code')
        address=_field(row,'Address','Street Address')
        nmls=_digits(license_no)
        if not name or not state or not nmls:
            rejected+=1; continue
        key=(nmls,name.lower(),state)
        if key in seen: continue
        seen.add(key)
        records.append({'legal_name':name,'nmls_id':nmls,'city':city,'state':state,'postal_code':postal,'address1':address,
                        'source_record_id':license_no,'source_url':MO_EXPORT,
                        'verification_status':'Official Missouri regulator roster - verify in NMLS before outreach'})
    result=ingest_companies(conn,job_id,source_id,records)
    result.update({'source_rows':len(records),'filtered_out':rejected,'target_minimum':target_minimum,'finished_at':NOW()})
    return result


__all__=['import_missouri_broker_roster']
