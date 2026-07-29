import re, sqlite3
from pathlib import Path
from datetime import datetime

SEEDS = [
('fannie','Fannie Mae','Selling Guide','B3-4.3-04','Personal Gifts','https://selling-guide.fanniemae.com/sel/b3-4.3-04/personal-gifts','Personal gifts; gift funds; acceptable donors; minimum borrower contribution requirements; documentation requirements; verifying donor availability and transfer of gift funds. Gift funds are addressed for eligible principal residence and second-home transactions. Review the official section for occupancy, property-unit count, LTV and borrower-contribution requirements.'),
('fannie','Fannie Mae','Selling Guide','B3-4.3-05','Gifts of Equity','https://selling-guide.fanniemae.com/sel/b3-4.3-05/gifts-equity','Gifts of equity require a signed gift letter and the settlement statement must identify the gift of equity. Review the official section and Personal Gifts section for complete eligibility and documentation.'),
('fannie','Fannie Mae','Selling Guide','B3-6-05','Monthly Debt Obligations','https://selling-guide.fanniemae.com/sel/b3-6-05/monthly-debt-obligations','Monthly debt obligations used in the debt-to-income ratio, including installment debt, revolving debt, student loans, lease payments, alimony, child support and other recurring obligations.'),
('fannie','Fannie Mae','Selling Guide','B3-3.1-09','Other Sources of Income','https://selling-guide.fanniemae.com/sel/b3-3.1-09/other-sources-income','Requirements for documenting and calculating other income sources. Use the exact subsection for commission, bonus, overtime, boarder, retirement, disability, unemployment and related income types.'),
('fannie','Fannie Mae','Selling Guide','B3-3.2-01','Underwriting Factors and Documentation for a Self-Employed Borrower','https://selling-guide.fanniemae.com/sel/b3-3.2-01/underwriting-factors-and-documentation-self-employed-borrower','Analysis and documentation requirements for self-employed borrowers, including history, stability, tax returns, business income and liquidity considerations.'),
('fannie','Fannie Mae','Selling Guide','B2-1.3-02','Limited Cash-Out Refinance Transactions','https://selling-guide.fanniemae.com/sel/b2-1.3-02/limited-cash-out-refinance-transactions','Eligibility and proceeds requirements for limited cash-out refinance transactions.'),
('fannie','Fannie Mae','Selling Guide','B2-1.3-03','Cash-Out Refinance Transactions','https://selling-guide.fanniemae.com/sel/b2-1.3-03/cash-out-refinance-transactions','Eligibility, ownership and proceeds requirements for cash-out refinance transactions, including delayed financing exceptions.'),
('freddie','Freddie Mac','Seller/Servicer Guide','5401.2','Monthly debt payment-to-income ratio','https://guide.freddiemac.com/app/guide/section/5401.2','Requirements for calculating monthly debt payment-to-income ratio. Includes student loans, installment debt, revolving accounts, lease payments, alimony, child support and circumstances where debts may be excluded. Student-loan treatment depends on the payment shown, repayment status and the specific Guide conditions.'),
('freddie','Freddie Mac','Seller/Servicer Guide','5501.3','Asset eligibility and documentation','https://guide.freddiemac.com/app/guide/section/5501.3','Requirements for eligible borrower assets and documentation, including funds needed to close, reserves and treatment of loans secured by financial assets.'),
('freddie','Freddie Mac','Seller/Servicer Guide','5501.5','Gifts','https://guide.freddiemac.com/app/guide/section/5501.5','Requirements for gift funds and gift letters, acceptable donors, transfer of funds, gifts of equity and borrower contribution where applicable. Review transaction occupancy and property type in the official section.'),
('freddie','Freddie Mac','Seller/Servicer Guide','5304.1','Self-employed income','https://guide.freddiemac.com/app/guide/section/5304.1','General requirements for analysis and documentation of self-employed income.'),
('freddie','Freddie Mac','Seller/Servicer Guide','4203.4','Temporary subsidy buydown plans','https://guide.freddiemac.com/app/guide/section/4203.4','Requirements for temporary subsidy buydown plans, including qualification and documentation.'),
('va','VA','VA Lenders Handbook','Chapter 4','Credit Underwriting','https://www.benefits.va.gov/warms/pam26_7.asp','VA credit underwriting addresses income, debts, credit history, debt-to-income ratio and residual income. Residual income is evaluated by loan amount, family size and geographic region. The handbook explains compensating factors and the relationship between DTI and residual income.'),
('va','VA','VA Lenders Handbook','Chapter 3','The VA Loan and Guaranty','https://www.benefits.va.gov/warms/pam26_7.asp','VA guaranty, entitlement, maximum guaranty and loan structure requirements.'),
('va','VA','VA Lenders Handbook','Chapter 5','How to Process VA Loans and Submit Them to VA','https://www.benefits.va.gov/warms/pam26_7.asp','Processing and submission requirements for VA-guaranteed loans, including documentation and lender responsibilities.'),
('va','VA','VA Lenders Handbook','Chapter 9','Legal Instruments, Liens, Escrows, and Related Issues','https://www.benefits.va.gov/warms/pam26_7.asp','Requirements involving legal instruments, liens, escrows, sales contracts and related loan-closing issues, including applicable VA clauses.'),
('usda','USDA','HB-1-3555','Chapter 8','Applicant Characteristics','https://www.rd.usda.gov/resources/directives/handbooks','Applicant eligibility, income, citizenship or qualified-alien requirements, ownership of other property and ability to obtain conventional credit on reasonable terms.'),
('usda','USDA','HB-1-3555','Chapter 9','Income Analysis','https://www.rd.usda.gov/resources/directives/handbooks','Annual income, adjusted annual income and repayment income are distinct calculations. Household income is used for program eligibility while stable and dependable repayment income is used for qualifying.'),
('usda','USDA','HB-1-3555','Chapter 10','Credit Analysis','https://www.rd.usda.gov/resources/directives/handbooks','Credit analysis, ratios, GUS findings, manual underwriting and compensating-factor requirements.'),
('usda','USDA','HB-1-3555','Chapter 12','Property and Appraisal Requirements','https://www.rd.usda.gov/resources/directives/handbooks','General property eligibility and appraisal requirements for the Single Family Housing Guaranteed Loan Program.'),
('usda','USDA','HB-1-3555','Chapter 13','Special Property Types','https://www.rd.usda.gov/sites/default/files/3555-1chapter13.pdf','Requirements for special property situations, including manufactured homes. Review construction, installation, site, age, inspection and state/local requirements in the official chapter.'),
]

def ensure_schema(conn):
    conn.executescript('''
    create table if not exists guideline_documents(
      id integer primary key, program_key text, program text, source_type text,
      section text, title text, url text, content text, page integer default 0,
      source_date text default '', indexed_at text, unique(program_key,section,title,page)
    );
    create virtual table if not exists guideline_fts using fts5(
      title, section, content, program, source_type,
      content='guideline_documents', content_rowid='id', tokenize='porter unicode61'
    );
    create trigger if not exists guideline_ai after insert on guideline_documents begin
      insert into guideline_fts(rowid,title,section,content,program,source_type)
      values(new.id,new.title,new.section,new.content,new.program,new.source_type);
    end;
    create trigger if not exists guideline_ad after delete on guideline_documents begin
      insert into guideline_fts(guideline_fts,rowid,title,section,content,program,source_type)
      values('delete',old.id,old.title,old.section,old.content,old.program,old.source_type);
    end;
    create trigger if not exists guideline_au after update on guideline_documents begin
      insert into guideline_fts(guideline_fts,rowid,title,section,content,program,source_type)
      values('delete',old.id,old.title,old.section,old.content,old.program,old.source_type);
      insert into guideline_fts(rowid,title,section,content,program,source_type)
      values(new.id,new.title,new.section,new.content,new.program,new.source_type);
    end;
    ''')

def seed_index(conn):
    ensure_schema(conn)
    now=datetime.now().isoformat(timespec='seconds')
    for row in SEEDS:
        conn.execute('''insert or ignore into guideline_documents
        (program_key,program,source_type,section,title,url,content,page,source_date,indexed_at)
        values(?,?,?,?,?,?,?,?,?,?)''',(*row,0,'',now))
    conn.commit()

def index_fha_pdf(conn, pdf_path):
    p=Path(pdf_path)
    if not p.exists(): return 0
    existing=conn.execute("select count(*) from guideline_documents where program_key='fha' and source_type='Handbook 4000.1 PDF'").fetchone()[0]
    if existing>100:return existing
    try:
        from pypdf import PdfReader
        reader=PdfReader(str(p)); now=datetime.now().isoformat(timespec='seconds'); n=0
        for page_no,page in enumerate(reader.pages,1):
            text=' '.join((page.extract_text() or '').split())
            if len(text)<80: continue
            # Keep page-sized authoritative chunks; title is inferred from the first meaningful line.
            title='FHA Single Family Housing Policy Handbook 4000.1'
            sec=''
            m=re.search(r'\b((?:II|III|IV|V|VI|VII|VIII|IX|X)(?:\.[A-Z0-9]+){1,7})\b',text[:700])
            if m: sec=m.group(1)
            conn.execute('''insert or ignore into guideline_documents
            (program_key,program,source_type,section,title,url,content,page,source_date,indexed_at)
            values('fha','FHA','Handbook 4000.1 PDF',?,?,?,?,?,?,?)''',
            (sec,title,'https://www.hud.gov/hud-partners/single-family-handbook-4000-1',text,page_no,'11/26/2025',now)); n+=1
            if n%100==0: conn.commit()
        conn.commit(); return n
    except Exception:
        return 0

def _fts_query(q):
    terms=re.findall(r'[A-Za-z0-9][A-Za-z0-9-]{1,}',q.lower())
    stop={'can','the','be','on','a','an','is','are','how','what','used','for','with','and','or','to','of','in'}
    terms=[t for t in terms if t not in stop][:12]
    return ' OR '.join('"'+t.replace('"','')+'"' for t in terms)

def search(conn, query, program='all', limit=20):
    seed_index(conn)
    fts=_fts_query(query)
    if not fts:return []
    qterms=[t for t in re.findall(r'[A-Za-z0-9][A-Za-z0-9-]{1,}',query.lower()) if t not in {'can','the','be','on','a','an','is','are','how','what','used','for','with','and','or','to','of','in'}]
    params=[fts]; where=''
    if program!='all': where=' and d.program_key=?'; params.append(program)
    params.append(max(limit*4,60))
    rows=conn.execute(f'''select d.*, bm25(guideline_fts,6.0,8.0,1.0,2.0,1.0) rank,
      snippet(guideline_fts,2,'<mark>','</mark>',' … ',55) snippet
      from guideline_fts join guideline_documents d on d.id=guideline_fts.rowid
      where guideline_fts match ? {where}
      order by rank limit ?''',params).fetchall()
    scored=[]
    program_alias={'fannie':['fannie','fnma'],'freddie':['freddie','fhlmc'],'fha':['fha','hud'],'va':['va','veteran'],'usda':['usda','rural']}
    query_programs={k for k,aliases in program_alias.items() if any(a in query.lower() for a in aliases)}
    for r in rows:
        d=dict(r); raw=d.pop('snippet') or d.get('content','')[:700]
        excerpt=re.sub(r'</?mark>','',raw,flags=re.I)
        hay=' '.join([d.get('title',''),d.get('section',''),d.get('content',''),d.get('program','')]).lower()
        matched=sorted({t for t in qterms if t in hay},key=lambda x:(-len(x),x))
        title_hay=(d.get('title','')+' '+d.get('section','')).lower()
        score=len(matched)*5 + sum(7 for t in matched if t in title_hay)
        if query_programs and d.get('program_key') in query_programs: score+=30
        if 'gift' in qterms and 'gift' in title_hay: score+=24
        if 'student' in qterms and 'student' in hay: score+=18
        if 'residual' in qterms and 'residual' in hay: score+=18
        if 'manufactured' in qterms and 'manufactured' in hay: score+=18
        # Penalize generic handbook pages when a titled guide section is available.
        if d.get('source_type')=='Handbook 4000.1 PDF' and len(matched)<2: score-=10
        d['excerpt']=excerpt; d['matched_terms']=matched[:8]
        d['display_url']=re.sub(r'^https?://','',d['url']); d.pop('content',None); d.pop('rank',None)
        scored.append((score,d))
    scored.sort(key=lambda x:(-x[0], x[1].get('page',0) or 0))
    return [d for score,d in scored[:limit] if score>0]

def stats(conn):
    ensure_schema(conn)
    rows=conn.execute('select program_key,program,count(*) n,max(indexed_at) indexed_at from guideline_documents group by program_key,program order by program').fetchall()
    return {'total':sum(r['n'] for r in rows),'programs':[dict(r) for r in rows]}
