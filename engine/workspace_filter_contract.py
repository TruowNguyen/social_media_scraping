"""Backend-owned choices and validation for saved-data workspace filters."""
from src.analysis.classification_contract import get_schema

INTENT_NAMES={'COMPLAINT':'Phản ánh / khiếu nại','ADVERTISING':'Quảng cáo','SALES':'Bán hàng',
    'RECRUITMENT':'Tuyển dụng','RENTAL':'Thuê / cho thuê','BUY_SELL':'Mua bán','LOAN_DEBT':'Vay nợ',
    'GOODS_EXCHANGE':'Trao đổi hàng hóa','INFORMATIONAL':'Thông tin / trao đổi','UNKNOWN':'Chưa rõ ý định'}
PROCESSING_NAMES={'PENDING':'Đang chờ','RUNNING':'Đang xử lý','DONE':'Hoàn thành','FAILED':'Lỗi phân loại',
    'STALE':'Cần phân loại lại','MISSING_TEXT':'Thiếu nội dung','OVERSIZED':'Vượt kích thước',
    'UNCLASSIFIED':'Chưa vào hàng chờ','FILTER_DROP':'Bộ lọc loại'}
ALLOWED={'keyword','project_id','source_id','issue_id','intent','node_type','review','quality','ocr_status',
    'relevance','processing_status','project_basis','date_basis','start_date','end_date','sort','time_status','run_id','platform','query_id'}


def choices():
    ids=get_schema('classification-result-v2')['$defs']['result']['properties']['content_intents']['items']['enum']
    return {'intents':[{'id':i,'name':INTENT_NAMES[i]} for i in ids],
        'processing_statuses':[{'id':i,'name':name} for i,name in PROCESSING_NAMES.items()]}


def validate(filters,registry,taxonomy):
    unknown=set(filters)-ALLOWED
    if unknown:raise ValueError('Bộ lọc không được hệ thống hỗ trợ: '+', '.join(sorted(unknown)))
    enums={'platform':{'facebook','threads'},'intent':set(INTENT_NAMES),'processing_status':set(PROCESSING_NAMES),
        'relevance':{'KEEP','DROP','REVIEW','UNCLASSIFIED'},'node_type':{'POST','COMMENT','REPLY'},
        'review':{'UNREVIEWED','RELEVANT','IRRELEVANT','NEEDS_REVIEW'},
        'quality':{'COMPLETE','PARTIAL','FAILED','REFERENCE_ONLY'},
        'ocr_status':{'NO_IMAGES','NOT_RUN','AVAILABLE','EMPTY','FAILED','UNAVAILABLE','NEEDS_REVIEW','PARTIAL'},
        'project_basis':{'MODEL','SOURCE'},'date_basis':{'published_at','observed_any','observed_latest','collected_at'},
        'time_status':{'INSTANT','UNKNOWN'},'sort':{'newest','oldest'}}
    for name,values in enums.items():
        if filters.get(name) and filters[name] not in values:raise ValueError('Lựa chọn bộ lọc không hợp lệ: '+name)
    if filters.get('source_id') and filters['source_id'] not in registry.sources:raise ValueError('Nguồn không có trong danh sách theo dõi.')
    if filters.get('query_id') and registry.sources.get(filters['query_id'],{}).get('source_type')!='THREADS_SEARCH':raise ValueError('Truy vấn không có trong danh sách Threads.')
    if filters.get('project_id') and filters['project_id'] not in {*taxonomy['profiles'],'__unknown__'}:raise ValueError('Dự án không có trong taxonomy.')
    if filters.get('issue_id') and filters['issue_id'] not in {i['issue_id'] for i in taxonomy['catalog']['issues']}:raise ValueError('Nhóm vấn đề không có trong taxonomy.')
    if len(filters.get('keyword',''))>300:raise ValueError('Từ khóa tối đa 300 ký tự.')
