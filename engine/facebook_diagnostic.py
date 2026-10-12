"""Read-only native diagnostics; output counts/status only, never session values."""
import argparse
import json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from engine.registry import Registry
from src.acquisition.browser import browser_job,navigate,page_failure
from src.acquisition.browser_adapters import FacebookGroupAdapter,candidate_from_row
from src.acquisition.facebook_threads import collect_rows
from src.acquisition.models import Deadline,AdapterError,Window,DiscoveryRequest,FetchContext,utcnow


def diagnose(source,post_url,output):
    deadline=Deadline(120)
    now=datetime.now(timezone.utc)
    window=Window(now-timedelta(days=7),now)
    report={'checked_at':utcnow(),'source_id':source['source_id'],'mode':'NATIVE_FACEBOOK_BROWSER_HEADLESS',
        'cookie_values_logged':False,'checks':[]}
    try:
        with browser_job('facebook',deadline) as page:
            # Presence only; not evidence the session is valid and no cookie value leaves memory.
            report['authentication_cookie_present']=any(c['name']=='c_user' for c in page.context.cookies('https://www.facebook.com'))
            adapter=FacebookGroupAdapter(page,deadline)
            def observe(label,url):
                child=Deadline(30,deadline)
                check={'target':label,'url':url}
                try:
                    navigate(page,url,child)
                    page.wait_for_timeout(child.milliseconds(3000))
                    failure=page_failure(page)
                    if failure: raise AdapterError(*failure)
                    check['status']='PAGE_LOADED'
                except AdapterError as error:
                    check.update(status=error.status,error_code=error.code)
                rows=adapter.listing_rows()
                check.update(articles=page.locator('[role="article"]').count(),
                    story_or_card_rows=len(rows),caption_rows=sum(bool(r.get('caption')) for r in rows),
                    own_publication_rows=sum(bool(r.get('epoch') or r.get('datetime')) for r in rows),
                    comment_links=page.locator('a[href*="comment_id="]').count())
                report['checks'].append(check)
                page.screenshot(path=str(output.with_name(output.stem+'-'+label+'.png')),full_page=False)
                return check
            first=observe('original-post',post_url)
            if first['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED'}:
                report['stop_reason']='ACCESS_BLOCKER'
            else:
                group=observe('group',source['url'])
                if group['status']=='PAGE_LOADED':
                    request=DiscoveryRequest(source,'diagnostic',window,deadline,'RECENT_SOURCE_ITEMS')
                    found={}
                    for row in adapter.listing_rows():
                        candidate=candidate_from_row(row,request,'facebook')
                        if candidate and candidate.canonical_url!=post_url: found[candidate.canonical_url]=candidate
                    report['other_post_links_observed']=len(found)
                    for index,candidate in enumerate(list(found.values())[:2]):
                        check=observe('other-post-'+str(index+1),candidate.canonical_url)
                        if check['status']=='PAGE_LOADED':
                            try:
                                adapter.deadline=Deadline(20,deadline)
                                fetched=adapter.fetch_item(candidate,FetchContext(source,window,adapter.deadline,raw_first=True)).candidate
                                check.update(fetch_status='FETCHED' if fetched.raw_text else 'METADATA_ONLY',
                                    caption_length=len(fetched.raw_text or ''),publication_precision=fetched.publication_precision,
                                    published_at=fetched.published_at,
                                    comment_nodes_parsed=len(collect_rows(page,candidate.canonical_url,candidate.platform_item_id)))
                            except AdapterError as error:
                                check.update(fetch_status=error.status,fetch_error_code=error.code)
                        if check['status'] in {'AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED'}: break
    except AdapterError as error:
        report.update(status=error.status,error_code=error.code)
    except Exception:
        report.update(status='DIAGNOSTIC_FAILED',error_code='UNEXPECTED_DIAGNOSTIC_ERROR')
    report['finished_at']=utcnow()
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-id',required=True)
    parser.add_argument('--post-url',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from src.acquisition.identity import identify,source_references
    registry=Registry('config');source=registry.sources[args.source_id]
    target=identify(args.post_url)
    if source['source_type']!='FACEBOOK_GROUP' or registry.readiness(source) or target.origin not in source_references(source) or not target.item_id:
        raise ValueError('Verified enabled Facebook group and its post required')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    print(json.dumps(diagnose(source,args.post_url,args.output),ensure_ascii=False))


if __name__=='__main__': main()
