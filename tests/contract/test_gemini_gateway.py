import json
import unittest
from src.analysis.gemini_gateway import GeminiGateway,ProviderError


class Response:
    def __init__(self,status=200,body=None):
        self.status_code=status;self.body=body or {'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'prompt_tokens':12,'secret':'must not log'}}
        self.content=json.dumps(self.body).encode();self.closed=False
    def json(self):return self.body
    def close(self):self.closed=True


class HTTP:
    def __init__(self,response):self.response=response;self.kwargs=None
    def post(self,url,**kwargs):self.url=url;self.kwargs=kwargs;return self.response


class ProviderTests(unittest.TestCase):
    def request(self):return {'batch_id':'batch','items':[{}]}
    def provider(self,response):
        self.http=HTTP(response)
        return GeminiGateway('https://gateway.invalid/v1','sensitive-test-key','configured-model',http=self.http)

    def test_protocol_no_redirects_no_secrets_in_telemetry(self):
        response=Response();provider=self.provider(response)
        self.assertEqual(provider(self.request()),'{}')
        self.assertEqual(self.http.url,'https://gateway.invalid/v1/chat/completions')
        self.assertFalse(self.http.kwargs['allow_redirects'])
        self.assertTrue(response.closed)
        self.assertNotIn('sensitive-test-key',json.dumps(provider.telemetry))
        self.assertNotIn('secret',provider.telemetry[0]['usage'])

    def test_ocr_constraints_include_parent_images_without_changing_request(self):
        request = {'batch_id':'batch','items':[
            {'item_id':'plain'},
            {'item_id':'accepted','image_evidence':[{'quality_status':'ACCEPTABLE','role':'TARGET'}]},
            {'item_id':'parent-ocr','image_evidence':[{'quality_status':'NEEDS_REVIEW','role':'ROOT_POST'}]},
            {'item_id':'target-ocr','image_evidence':[{'quality_status':'UNKNOWN','role':'TARGET'}]}]}
        original = json.dumps(request)
        provider = self.provider(Response())
        provider(request)
        user = json.loads(self.http.kwargs['json']['messages'][1]['content'])
        hints = user['validation_constraints']
        self.assertEqual(hints['uncertain_ocr_item_ids'],['parent-ocr','target-ocr'])
        self.assertEqual(hints['uncertain_ocr_required_state']['allowed_relevance'],['KEEP','REVIEW'])
        self.assertTrue(hints['uncertain_ocr_required_state']['needs_review'])
        self.assertEqual(user['request'],request)
        self.assertEqual(json.dumps(request),original)

    def test_auth_fails_without_retry_and_temporary_failure_retries(self):
        for status,retryable in ((401,False),(429,True),(503,True)):
            response=Response(status);provider=self.provider(response)
            with self.assertRaises(ProviderError) as error:provider(self.request())
            self.assertEqual(error.exception.retryable,retryable);self.assertTrue(response.closed)

    def test_truncated_output_never_accepted(self):
        provider=self.provider(Response(body={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]}))
        with self.assertRaises(ProviderError) as error:provider(self.request())
        self.assertEqual(error.exception.code,'PROVIDER_OUTPUT_TRUNCATED')

    def test_protocol_invalid_or_non_https_config_fails(self):
        provider=self.provider(Response(body={'error':{'message':'sensitive-provider-body'}}))
        with self.assertRaises(ProviderError) as error:provider(self.request())
        self.assertNotIn('sensitive',str(error.exception))
        with self.assertRaises(ProviderError):GeminiGateway('http://gateway.invalid/v1','key','model')
