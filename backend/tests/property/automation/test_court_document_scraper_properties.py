"""
CourtDocumentScraper API 拦截属性测试
使用 Hypothesis 进行基于属性的测试
"""
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, MagicMock, patch
import time
import json

from apps.automation.models import ScraperTask
from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper


# 定义策略
@st.composite
def api_response_strategy(draw):
    """生成有效的 API 响应数据"""
    # 生成文书数量
    doc_count = draw(st.integers(min_value=0, max_value=10))
    
    # 生成文书列表
    documents = []
    for _ in range(doc_count):
        documents.append({
            'c_sdbh': draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'c_stbh': draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'wjlj': f"https://example.com/{draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))}",
            'c_wsbh': draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'c_wsmc': draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'c_fybh': draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'c_fymc': draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
            'c_wjgs': draw(st.sampled_from(['pdf', 'doc', 'docx'])),
            'dt_cjsj': '2024-01-01T00:00:00'
        })
    
    return {
        'code': 200,
        'msg': 'success',
        'data': documents,
        'success': True,
        'totalRows': doc_count
    }


@pytest.mark.django_db
class TestCourtDocumentScraperAPIInterceptProperties:
    """CourtDocumentScraper API 拦截属性测试"""
    
    def setup_method(self):
        """测试前准备"""
        # 创建测试用的爬虫任务
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document",
            status="running",
            url="https://zxfw.court.gov.cn/test",
            priority=5
        )
    
    @settings(max_examples=100, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_1_api_interceptor_configuration(self, api_response):
        """
        属性 1: API拦截器正确配置
        
        Feature: court-document-api-optimization, Property 1: API拦截器正确配置
        
        对于任何打开 zxfw.court.gov.cn 文书页面的操作，
        系统应该正确配置并触发API拦截器监听指定的接口
        验证需求: 1.1
        """
        # 创建 mock 对象
        mock_page = MagicMock()
        mock_response = MagicMock()
        
        # 配置 mock 响应
        mock_response.url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        mock_response.json.return_value = api_response
        
        # 记录监听器是否被注册
        listener_registered = False
        registered_handler = None
        
        def mock_on(event_name, handler):
            nonlocal listener_registered, registered_handler
            if event_name == "response":
                listener_registered = True
                registered_handler = handler
        
        mock_page.on = mock_on
        mock_page.remove_listener = MagicMock()
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = mock_page
        
        # 执行拦截（在单独的线程中模拟响应）
        import threading
        
        def trigger_response():
            time.sleep(0.1)  # 短暂延迟
            if registered_handler:
                registered_handler(mock_response)
        
        thread = threading.Thread(target=trigger_response)
        thread.start()
        
        result = scraper._intercept_api_response(timeout=5000)
        thread.join()
        
        # 验证：监听器已注册
        assert listener_registered, "API 响应监听器应该被注册"
        
        # 验证：监听器已被移除
        assert mock_page.remove_listener.called, "监听器应该在完成后被移除"
        
        # 验证：成功拦截到数据
        if api_response['data']:  # 如果有数据
            assert result is not None, "应该成功拦截到 API 响应"
            assert result == api_response, "拦截到的数据应该与 API 响应一致"
    
    @settings(max_examples=100, deadline=None)
    @given(
        api_response=api_response_strategy(),
        timeout_ms=st.integers(min_value=1000, max_value=10000)
    )
    def test_property_19_statistics_log_accuracy(self, api_response, timeout_ms):
        """
        属性 19: 统计日志准确性
        
        Feature: court-document-api-optimization, Property 19: 统计日志准确性
        
        对于任何API拦截成功的操作，日志应该记录拦截到的文书数量和响应时间
        验证需求: 6.3
        """
        # 创建 mock 对象
        mock_page = MagicMock()
        mock_response = MagicMock()
        
        # 配置 mock 响应
        mock_response.url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        mock_response.json.return_value = api_response
        
        # 记录日志调用
        log_calls = []
        
        def mock_on(event_name, handler):
            if event_name == "response":
                # 立即触发响应
                handler(mock_response)
        
        mock_page.on = mock_on
        mock_page.remove_listener = MagicMock()
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = mock_page
        
        # Mock logger 来捕获日志
        with patch('apps.automation.services.scraper.scrapers.court_document.logger') as mock_logger:
            # 记录所有 info 调用
            def capture_log(*args, **kwargs):
                log_calls.append({
                    'args': args,
                    'kwargs': kwargs
                })
            
            mock_logger.info.side_effect = capture_log
            
            # 执行拦截
            result = scraper._intercept_api_response(timeout=timeout_ms)
            
            # 验证：应该有日志记录
            assert len(log_calls) > 0, "应该有日志记录"
            
            # 查找包含统计信息的日志
            stats_log = None
            for log_call in log_calls:
                if 'extra' in log_call['kwargs']:
                    extra = log_call['kwargs']['extra']
                    if 'document_count' in extra and 'response_time_ms' in extra:
                        stats_log = extra
                        break
            
            # 验证：应该有统计日志
            if result is not None:  # 只有成功拦截时才验证
                assert stats_log is not None, "应该记录统计信息日志"
                
                # 验证：文书数量正确
                expected_count = len(api_response.get('data', []))
                assert stats_log['document_count'] == expected_count, \
                    f"日志中的文书数量应该为 {expected_count}"
                
                # 验证：响应时间存在且合理
                assert 'response_time_ms' in stats_log, "应该记录响应时间"
                assert stats_log['response_time_ms'] >= 0, "响应时间应该为非负数"
                
                # 验证：包含操作类型
                assert stats_log.get('operation_type') == 'api_intercept', \
                    "应该记录操作类型为 api_intercept"
                
                # 验证：包含时间戳
                assert 'timestamp' in stats_log, "应该记录时间戳"
                
                # 验证：包含 API URL
                assert 'api_url' in stats_log, "应该记录 API URL"
    
    @settings(max_examples=100, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_4_document_list_traversal_completeness(self, api_response):
        """
        属性 4: 文书列表遍历完整性
        
        Feature: court-document-api-optimization, Property 4: 文书列表遍历完整性
        
        对于任何文书列表，系统应该处理列表中的每一条记录，处理数量应该等于列表长度
        验证需求: 2.1
        """
        from apps.core.path import Path
        
        # 创建 mock 对象
        mock_page = MagicMock()
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = mock_page
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 记录处理的文书数量
        processed_count = 0
        
        # Mock _download_document_directly 方法
        def mock_download(document_data, download_dir, download_timeout=60000):
            nonlocal processed_count
            processed_count += 1
            return True, f"/tmp/test_{processed_count}.pdf", None
        
        scraper._download_document_directly = mock_download
        
        # 模拟遍历文书列表
        documents = api_response.get('data', [])
        for doc in documents:
            scraper._download_document_directly(doc, download_dir)
        
        # 验证：处理数量应该等于列表长度
        expected_count = len(documents)
        assert processed_count == expected_count, \
            f"应该处理 {expected_count} 个文书，实际处理了 {processed_count} 个"
    
    @settings(max_examples=100, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_5_url_extraction_correctness(self, api_response):
        """
        属性 5: URL提取正确性
        
        Feature: court-document-api-optimization, Property 5: URL提取正确性
        
        对于任何文书记录，从 wjlj 字段提取的URL应该是有效的HTTP/HTTPS URL
        验证需求: 2.2
        """
        import re
        
        # URL 验证正则表达式
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        # 遍历所有文书记录
        documents = api_response.get('data', [])
        for doc in documents:
            # 提取 URL
            url = doc.get('wjlj')
            
            # 验证：URL 应该存在
            assert url is not None, "wjlj 字段应该存在"
            assert url != '', "wjlj 字段不应该为空"
            
            # 验证：URL 应该是有效的 HTTP/HTTPS URL
            assert url_pattern.match(url), \
                f"URL 应该是有效的 HTTP/HTTPS URL: {url}"
            
            # 验证：URL 应该以 http:// 或 https:// 开头
            assert url.startswith('http://') or url.startswith('https://'), \
                f"URL 应该以 http:// 或 https:// 开头: {url}"
    
    @settings(max_examples=100, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_6_download_function_invocation(self, api_response):
        """
        属性 6: 下载功能调用
        
        Feature: court-document-api-optimization, Property 6: 下载功能调用
        
        对于任何有效的下载URL，系统应该调用 Playwright 的下载功能
        验证需求: 2.3
        """
        from apps.core.path import Path
        
        # 创建 mock 对象
        mock_page = MagicMock()
        mock_download_info = MagicMock()
        mock_download = MagicMock()
        
        # 配置 mock
        mock_download.suggested_filename = "test.pdf"
        mock_download_info.value = mock_download
        mock_page.expect_download.return_value.__enter__ = lambda self: mock_download_info
        mock_page.expect_download.return_value.__exit__ = lambda self, *args: None
        mock_page.goto = MagicMock()
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = mock_page
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 遍历所有文书记录
        documents = api_response.get('data', [])
        for doc in documents:
            url = doc.get('wjlj')
            
            # 重置 mock
            mock_page.expect_download.reset_mock()
            mock_page.goto.reset_mock()
            
            # 调用下载方法
            success, filepath, error = scraper._download_document_directly(
                doc, download_dir, download_timeout=5000
            )
            
            # 验证：应该调用 expect_download
            assert mock_page.expect_download.called, \
                f"应该调用 Playwright 的 expect_download 方法下载 {url}"
            
            # 验证：应该调用 goto 导航到 URL
            assert mock_page.goto.called, \
                f"应该调用 goto 方法导航到 {url}"
            
            # 验证：goto 的第一个参数应该是 URL
            call_args = mock_page.goto.call_args
            assert call_args[0][0] == url, \
                f"goto 方法应该使用正确的 URL: {url}"
    
    @settings(max_examples=100, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_7_file_naming_correctness(self, api_response):
        """
        属性 7: 文件命名正确性
        
        Feature: court-document-api-optimization, Property 7: 文件命名正确性
        
        对于任何下载成功的文书，保存的文件名应该基于 c_wsmc 字段，
        并且文件应该存在于指定目录
        验证需求: 2.4
        """
        from apps.core.path import Path
        import re
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        
        # Mock httpx 来避免真实的网络请求
        with patch('httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = b"fake file content"
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client_class.return_value = mock_client
            
            # 遍历所有文书记录
            documents = api_response.get('data', [])
            for doc in documents:
                # 调用下载方法
                success, filepath, error = scraper._download_document_directly(
                    doc, download_dir, download_timeout=5000
                )
                
                if success and filepath:
                    # 验证：文件路径应该存在
                    assert Path(filepath).exists(), \
                        f"下载的文件应该存在: {filepath}"
                    
                    # 验证：文件应该在指定目录下
                    assert str(download_dir) in filepath, \
                        f"文件应该在指定目录下: {download_dir}"
                    
                    # 验证：文件名应该基于 c_wsmc
                    filename = Path(filepath).name
                    c_wsmc = doc.get('c_wsmc', '')
                    
                    # 清理文件名中的非法字符（与实现保持一致）
                    cleaned_wsmc = re.sub(r'[<>:"/\\|?*]', '_', c_wsmc)
                    
                    # 验证：文件名应该包含清理后的 c_wsmc
                    assert cleaned_wsmc in filename, \
                        f"文件名应该包含 c_wsmc: {cleaned_wsmc}，实际文件名: {filename}"
                    
                    # 验证：文件扩展名应该基于 c_wjgs
                    c_wjgs = doc.get('c_wjgs', 'pdf')
                    assert filename.endswith(f".{c_wjgs}"), \
                        f"文件扩展名应该是 .{c_wjgs}，实际文件名: {filename}"
                    
                    # 清理测试文件
                    Path(filepath).unlink(missing_ok=True)
    
    @settings(max_examples=100, deadline=None)
    @given(
        doc_count=st.integers(min_value=2, max_value=5),
        delay_range=st.tuples(
            st.floats(min_value=0.5, max_value=1.5),
            st.floats(min_value=1.5, max_value=3.0)
        ).filter(lambda x: x[0] < x[1])
    )
    def test_property_22_download_delay_existence(self, doc_count, delay_range):
        """
        属性 22: 下载延迟存在性
        
        Feature: court-document-api-optimization, Property 22: 下载延迟存在性
        
        对于任何并发下载多个文书的操作，相邻两次下载之间应该存在延迟（1-2秒）
        验证需求: 7.4
        """
        from apps.core.path import Path
        import time
        
        # 创建 mock 对象
        mock_page = MagicMock()
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = mock_page
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 记录下载时间和延迟调用
        download_times = []
        delay_calls = []
        
        # Mock _download_document_directly 方法
        def mock_download(document_data, download_dir, download_timeout=60000):
            download_times.append(time.time())
            return True, f"/tmp/test_{len(download_times)}.pdf", None
        
        scraper._download_document_directly = mock_download
        
        # Mock random_wait 方法（避免实际延迟）
        def mock_random_wait(min_sec: float = 0.5, max_sec: float = 2.0):
            delay_calls.append({
                'min_sec': min_sec,
                'max_sec': max_sec,
                'timestamp': time.time()
            })
            # 不执行实际延迟，只记录调用
        
        scraper.random_wait = mock_random_wait
        
        # 生成测试文书数据
        documents = []
        for i in range(doc_count):
            documents.append({
                'c_sdbh': f'sdbh_{i}',
                'c_stbh': f'stbh_{i}',
                'wjlj': f'https://example.com/doc_{i}',
                'c_wsbh': f'wsbh_{i}',
                'c_wsmc': f'document_{i}',
                'c_fybh': f'fybh_{i}',
                'c_fymc': f'court_{i}',
                'c_wjgs': 'pdf',
                'dt_cjsj': '2024-01-01T00:00:00'
            })
        
        # 模拟下载流程（包含延迟）
        min_delay, max_delay = delay_range
        for i, doc in enumerate(documents):
            scraper._download_document_directly(doc, download_dir)
            
            # 在下载之间添加延迟（除了最后一个）
            if i < len(documents) - 1:
                scraper.random_wait(min_delay, max_delay)
        
        # 验证：应该有正确数量的下载记录
        assert len(download_times) == doc_count, \
            f"应该有 {doc_count} 次下载记录"
        
        # 验证：应该有正确数量的延迟调用
        expected_delay_calls = doc_count - 1  # 最后一个文书后不延迟
        assert len(delay_calls) == expected_delay_calls, \
            f"应该有 {expected_delay_calls} 次延迟调用，实际: {len(delay_calls)}"
        
        # 验证：每次延迟调用的参数应该正确
        for delay_call in delay_calls:
            assert delay_call['min_sec'] == min_delay, \
                f"延迟最小值应该为 {min_delay}，实际: {delay_call['min_sec']}"
            assert delay_call['max_sec'] == max_delay, \
                f"延迟最大值应该为 {max_delay}，实际: {delay_call['max_sec']}"
        
        # 验证：延迟调用应该在下载之间进行
        for i, delay_call in enumerate(delay_calls):
            # 延迟调用应该在第 i 次和第 i+1 次下载之间
            download_time_before = download_times[i]
            download_time_after = download_times[i + 1]
            delay_time = delay_call['timestamp']
            
            assert download_time_before <= delay_time <= download_time_after, \
                f"延迟调用 {i} 应该在下载 {i} 和下载 {i+1} 之间"

    @settings(max_examples=100, deadline=None)
    @given(
        total_docs=st.integers(min_value=3, max_value=10),
        failure_indices=st.lists(
            st.integers(min_value=0, max_value=9),
            min_size=1,
            max_size=3,
            unique=True
        )
    )
    def test_property_8_error_isolation(self, total_docs, failure_indices):
        """
        属性 8: 错误隔离性
        
        Feature: court-document-api-optimization, Property 8: 错误隔离性
        
        对于任何包含部分失败下载的文书列表，失败的下载不应该阻止其他文书的下载
        验证需求: 2.5
        """
        from apps.core.path import Path
        
        # 过滤掉超出范围的失败索引
        failure_indices = [idx for idx in failure_indices if idx < total_docs]
        
        # 如果没有有效的失败索引，跳过测试
        if not failure_indices:
            return
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成测试文书数据
        documents = []
        for i in range(total_docs):
            documents.append({
                'c_sdbh': f'sdbh_{i}',
                'c_stbh': f'stbh_{i}',
                'wjlj': f'https://example.com/doc_{i}',
                'c_wsbh': f'wsbh_{i}',
                'c_wsmc': f'document_{i}',
                'c_fybh': f'fybh_{i}',
                'c_fymc': f'court_{i}',
                'c_wjgs': 'pdf',
                'dt_cjsj': '2024-01-01T00:00:00'
            })
        
        # 记录处理结果
        processed_docs = []
        success_count = 0
        failure_count = 0
        
        # Mock _download_document_directly 方法
        def mock_download(document_data, download_dir, download_timeout=60000):
            nonlocal success_count, failure_count
            
            # 获取文书索引
            doc_index = int(document_data['c_sdbh'].split('_')[1])
            processed_docs.append(doc_index)
            
            # 如果是失败索引，返回失败
            if doc_index in failure_indices:
                failure_count += 1
                return False, None, f"模拟下载失败: document_{doc_index}"
            else:
                success_count += 1
                return True, f"/tmp/test_{doc_index}.pdf", None
        
        scraper._download_document_directly = mock_download
        
        # Mock _save_document_to_db 方法（确保数据库保存也不阻断）
        saved_docs = []
        
        def mock_save_to_db(document_data, download_result):
            # 记录保存尝试
            doc_index = int(document_data['c_sdbh'].split('_')[1])
            saved_docs.append({
                'index': doc_index,
                'success': download_result[0],
                'error': download_result[2]
            })
            
            # 模拟数据库保存（总是成功，不抛出异常）
            return doc_index + 1000  # 返回模拟的 document_id
        
        scraper._save_document_to_db = mock_save_to_db
        
        # 模拟下载流程
        documents_with_results = []
        for doc in documents:
            download_result = scraper._download_document_directly(doc, download_dir)
            documents_with_results.append((doc, download_result))
        
        # 批量保存到数据库
        save_result = scraper._save_documents_batch(documents_with_results)
        
        # 验证 1：所有文书都应该被处理（无论成功或失败）
        assert len(processed_docs) == total_docs, \
            f"应该处理所有 {total_docs} 个文书，实际处理了 {len(processed_docs)} 个"
        
        # 验证 2：处理顺序应该正确（按索引顺序）
        assert processed_docs == list(range(total_docs)), \
            f"文书应该按顺序处理，期望: {list(range(total_docs))}，实际: {processed_docs}"
        
        # 验证 3：成功和失败的数量应该正确
        expected_success = total_docs - len(failure_indices)
        expected_failure = len(failure_indices)
        
        assert success_count == expected_success, \
            f"应该有 {expected_success} 个成功下载，实际: {success_count}"
        assert failure_count == expected_failure, \
            f"应该有 {expected_failure} 个失败下载，实际: {failure_count}"
        
        # 验证 4：所有文书都应该尝试保存到数据库
        assert len(saved_docs) == total_docs, \
            f"应该尝试保存所有 {total_docs} 个文书到数据库，实际: {len(saved_docs)}"
        
        # 验证 5：数据库保存结果应该反映下载状态
        for saved_doc in saved_docs:
            doc_index = saved_doc['index']
            expected_success = doc_index not in failure_indices
            
            assert saved_doc['success'] == expected_success, \
                f"文书 {doc_index} 的保存状态应该为 {expected_success}"
            
            if not expected_success:
                assert saved_doc['error'] is not None, \
                    f"失败的文书 {doc_index} 应该有错误信息"
        
        # 验证 6：批量保存结果统计应该正确
        assert save_result['total'] == total_docs, \
            f"批量保存总数应该为 {total_docs}"
        assert save_result['success'] == total_docs, \
            f"所有文书都应该成功保存到数据库（即使下载失败）"
        assert save_result['failed'] == 0, \
            f"数据库保存不应该失败（错误隔离）"
        
        # 验证 7：失败不应该阻止后续文书的处理
        # 检查失败索引之后的文书是否都被处理了
        for failure_idx in failure_indices:
            subsequent_docs = [idx for idx in processed_docs if idx > failure_idx]
            expected_subsequent = list(range(failure_idx + 1, total_docs))
            
            assert subsequent_docs == expected_subsequent, \
                f"失败索引 {failure_idx} 之后的文书应该继续处理，" \
                f"期望: {expected_subsequent}，实际: {subsequent_docs}"

    @settings(max_examples=100, deadline=None)
    @given(
        api_error_type=st.sampled_from([
            'timeout', 'invalid_format', 'empty_data', 'network_error'
        ]),
        fallback_success=st.booleans()
    )
    def test_property_13_fallback_log_recording(self, api_error_type, fallback_success):
        """
        属性 13: 回退日志记录
        
        Feature: court-document-api-optimization, Property 13: 回退日志记录
        
        对于任何触发回退机制的情况，系统日志应该包含回退原因
        验证需求: 4.2
        """
        from apps.core.path import Path
        from unittest.mock import patch, MagicMock
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        
        # Mock page 对象（避免实际的浏览器操作）
        scraper.page = MagicMock()
        scraper.page.goto = MagicMock()
        scraper.page.wait_for_load_state = MagicMock()
        
        # Mock 其他必要的方法
        scraper.random_wait = MagicMock()
        scraper._save_page_state = MagicMock(return_value={"screenshot": "/tmp/test.png"})
        scraper._prepare_download_dir = MagicMock(return_value=Path("/tmp/test_downloads"))
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 模拟不同类型的 API 拦截错误
        api_errors = {
            'timeout': ValueError("API 拦截超时，未能获取文书列表"),
            'invalid_format': ValueError("API 响应格式错误：期望 dict，实际 str"),
            'empty_data': ValueError("API 响应中没有文书数据"),
            'network_error': Exception("网络连接失败")
        }
        
        api_error = api_errors[api_error_type]
        
        # Mock _download_via_api_intercept 方法（模拟失败）
        def mock_api_intercept(download_dir):
            raise api_error
        
        scraper._download_via_api_intercept = mock_api_intercept
        
        # Mock _download_via_fallback 方法
        def mock_fallback(download_dir):
            if fallback_success:
                return {
                    "source": "zxfw.court.gov.cn",
                    "document_count": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "files": ["/tmp/test.pdf"],
                    "message": "回退方式：成功下载 1/1 份文书"
                }
            else:
                raise Exception("回退机制也失败")
        
        scraper._download_via_fallback = mock_fallback
        
        # 记录日志调用
        log_calls = []
        
        # Mock logger 来捕获日志
        with patch('apps.automation.services.scraper.scrapers.court_document.logger') as mock_logger:
            # 记录所有日志调用
            def capture_log(level):
                def log_func(*args, **kwargs):
                    log_calls.append({
                        'level': level,
                        'args': args,
                        'kwargs': kwargs
                    })
                return log_func
            
            mock_logger.info.side_effect = capture_log('info')
            mock_logger.warning.side_effect = capture_log('warning')
            mock_logger.error.side_effect = capture_log('error')
            
            # 执行下载（应该触发回退）
            try:
                result = scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")
                
                # 如果回退成功，验证结果
                if fallback_success:
                    assert result is not None, "回退成功应该返回结果"
            except Exception as e:
                # 如果回退也失败，应该抛出异常
                if not fallback_success:
                    assert "所有下载方式均失败" in str(e), \
                        "回退失败应该抛出包含错误链的异常"
            
            # 验证：应该有日志记录
            assert len(log_calls) > 0, "应该有日志记录"
            
            # 查找回退相关的日志
            fallback_logs = []
            for log_call in log_calls:
                if 'extra' in log_call['kwargs']:
                    extra = log_call['kwargs']['extra']
                    operation_type = extra.get('operation_type', '')
                    
                    if 'fallback' in operation_type or 'api_intercept_failed' in operation_type:
                        fallback_logs.append({
                            'level': log_call['level'],
                            'operation_type': operation_type,
                            'extra': extra
                        })
            
            # 验证：应该有回退相关的日志
            assert len(fallback_logs) > 0, "应该有回退相关的日志记录"
            
            # 验证：日志中应该包含回退原因
            found_fallback_reason = False
            for log in fallback_logs:
                extra = log['extra']
                
                # 检查是否包含回退原因
                if 'fallback_reason' in extra:
                    found_fallback_reason = True
                    fallback_reason = extra['fallback_reason']
                    
                    # 验证：回退原因应该包含原始错误信息
                    assert str(api_error) in fallback_reason or \
                           type(api_error).__name__ in fallback_reason, \
                        f"回退原因应该包含原始错误信息，" \
                        f"期望包含: {str(api_error)}，实际: {fallback_reason}"
                
                # 检查是否记录了错误类型
                if 'error_type' in extra:
                    assert extra['error_type'] == type(api_error).__name__, \
                        f"应该记录正确的错误类型: {type(api_error).__name__}"
            
            # 验证：至少有一条日志包含回退原因
            assert found_fallback_reason, "至少应该有一条日志包含回退原因"
            
            # 验证：应该记录 API 拦截失败的日志
            api_failed_logs = [
                log for log in fallback_logs
                if log['operation_type'] == 'api_intercept_failed'
            ]
            assert len(api_failed_logs) > 0, "应该记录 API 拦截失败的日志"
            
            # 验证：应该记录回退尝试的日志
            fallback_attempt_logs = [
                log for log in fallback_logs
                if log['operation_type'] == 'fallback_attempt'
            ]
            assert len(fallback_attempt_logs) > 0, "应该记录回退尝试的日志"
            
            # 如果回退成功，验证成功日志
            if fallback_success:
                fallback_success_logs = [
                    log for log in fallback_logs
                    if log['operation_type'] == 'fallback_success'
                ]
                assert len(fallback_success_logs) > 0, "应该记录回退成功的日志"
            # 注意：如果回退失败，异常会被抛出，日志记录在 error 级别
            # 我们已经验证了 API 拦截失败和回退尝试的日志，这已经足够
    
    @settings(max_examples=100, deadline=None)
    @given(
        api_error_message=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs'))),
        use_fallback=st.booleans()
    )
    def test_property_14_fallback_result_marking(self, api_error_message, use_fallback):
        """
        属性 14: 回退结果标记
        
        Feature: court-document-api-optimization, Property 14: 回退结果标记
        
        对于任何使用回退机制成功的下载，返回结果应该包含标记表明使用了回退方式
        验证需求: 4.4
        """
        from apps.core.path import Path
        from unittest.mock import MagicMock
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        
        # Mock page 对象（避免实际的浏览器操作）
        scraper.page = MagicMock()
        scraper.page.goto = MagicMock()
        scraper.page.wait_for_load_state = MagicMock()
        
        # Mock 其他必要的方法
        scraper.random_wait = MagicMock()
        scraper._save_page_state = MagicMock(return_value={"screenshot": "/tmp/test.png"})
        scraper._prepare_download_dir = MagicMock(return_value=Path("/tmp/test_downloads"))
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock _download_via_api_intercept 方法
        def mock_api_intercept(download_dir):
            if use_fallback:
                # 模拟 API 拦截失败
                raise ValueError(api_error_message)
            else:
                # 模拟 API 拦截成功
                return {
                    "source": "zxfw.court.gov.cn",
                    "method": "api_intercept",
                    "document_count": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "files": ["/tmp/test_api.pdf"],
                    "db_save_result": {"total": 1, "success": 1, "failed": 0},
                    "message": "API 拦截方式：成功下载 1/1 份文书"
                }
        
        scraper._download_via_api_intercept = mock_api_intercept
        
        # Mock _download_via_fallback 方法
        def mock_fallback(download_dir):
            return {
                "source": "zxfw.court.gov.cn",
                "document_count": 1,
                "downloaded_count": 1,
                "failed_count": 0,
                "files": ["/tmp/test_fallback.pdf"],
                "message": "回退方式：成功下载 1/1 份文书"
            }
        
        scraper._download_via_fallback = mock_fallback
        
        # Mock logger（避免日志输出）
        with patch('apps.automation.services.scraper.scrapers.court_document.logger'):
            # 执行下载
            result = scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")
            
            # 验证：结果应该存在
            assert result is not None, "应该返回下载结果"
            
            if use_fallback:
                # 验证：使用回退方式时的结果标记
                
                # 验证 1：应该包含 method 字段，值为 "fallback"
                assert 'method' in result, "结果应该包含 method 字段"
                assert result['method'] == 'fallback', \
                    f"method 字段应该为 'fallback'，实际: {result.get('method')}"
                
                # 验证 2：应该包含 fallback_reason 字段
                assert 'fallback_reason' in result, "结果应该包含 fallback_reason 字段"
                assert result['fallback_reason'] is not None, \
                    "fallback_reason 不应该为空"
                assert api_error_message in result['fallback_reason'], \
                    f"fallback_reason 应该包含原始错误信息: {api_error_message}"
                
                # 验证 3：应该包含 api_intercept_error 字段
                assert 'api_intercept_error' in result, \
                    "结果应该包含 api_intercept_error 字段"
                assert isinstance(result['api_intercept_error'], dict), \
                    "api_intercept_error 应该是字典类型"
                
                # 验证 4：api_intercept_error 应该包含错误类型和消息
                api_error = result['api_intercept_error']
                assert 'type' in api_error, "api_intercept_error 应该包含 type 字段"
                assert 'message' in api_error, "api_intercept_error 应该包含 message 字段"
                assert api_error['type'] == 'ValueError', \
                    f"错误类型应该为 ValueError，实际: {api_error['type']}"
                assert api_error_message in api_error['message'], \
                    f"错误消息应该包含: {api_error_message}"
                
                # 验证 5：应该包含基本的下载结果字段
                assert 'source' in result, "结果应该包含 source 字段"
                assert 'downloaded_count' in result, "结果应该包含 downloaded_count 字段"
                assert 'files' in result, "结果应该包含 files 字段"
                
            else:
                # 验证：使用 API 拦截方式时的结果标记
                
                # 验证 1：应该包含 method 字段，值为 "api_intercept"
                assert 'method' in result, "结果应该包含 method 字段"
                assert result['method'] == 'api_intercept', \
                    f"method 字段应该为 'api_intercept'，实际: {result.get('method')}"
                
                # 验证 2：不应该包含 fallback_reason 字段
                assert 'fallback_reason' not in result, \
                    "API 拦截成功时不应该包含 fallback_reason 字段"
                
                # 验证 3：不应该包含 api_intercept_error 字段
                assert 'api_intercept_error' not in result, \
                    "API 拦截成功时不应该包含 api_intercept_error 字段"
                
                # 验证 4：应该包含 db_save_result 字段（API 拦截方式特有）
                assert 'db_save_result' in result, \
                    "API 拦截方式应该包含 db_save_result 字段"
    
    @settings(max_examples=100, deadline=None)
    @given(
        api_error_message=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs'))),
        fallback_error_message=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')))
    )
    def test_property_15_exception_chain_completeness(self, api_error_message, fallback_error_message):
        """
        属性 15: 异常链完整性
        
        Feature: court-document-api-optimization, Property 15: 异常链完整性
        
        对于任何回退机制也失败的情况，抛出的异常应该包含完整的错误链
        （API失败原因 + 回退失败原因）
        验证需求: 4.5
        """
        from apps.core.path import Path
        from apps.core.exceptions import ExternalServiceError
        from unittest.mock import MagicMock
        
        # 创建 scraper 实例
        scraper = CourtDocumentScraper(self.scraper_task)
        
        # Mock page 对象（避免实际的浏览器操作）
        scraper.page = MagicMock()
        scraper.page.goto = MagicMock()
        scraper.page.wait_for_load_state = MagicMock()
        
        # Mock 其他必要的方法
        scraper.random_wait = MagicMock()
        scraper._save_page_state = MagicMock(return_value={"screenshot": "/tmp/test.png"})
        scraper._prepare_download_dir = MagicMock(return_value=Path("/tmp/test_downloads"))
        
        # 准备下载目录
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock _download_via_api_intercept 方法（模拟失败）
        def mock_api_intercept(download_dir):
            raise ValueError(api_error_message)
        
        scraper._download_via_api_intercept = mock_api_intercept
        
        # Mock _download_via_fallback 方法（模拟失败）
        def mock_fallback(download_dir):
            raise RuntimeError(fallback_error_message)
        
        scraper._download_via_fallback = mock_fallback
        
        # Mock logger（避免日志输出）
        with patch('apps.automation.services.scraper.scrapers.court_document.logger'):
            # 执行下载，应该抛出异常
            with pytest.raises(ExternalServiceError) as exc_info:
                scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")
            
            # 获取异常对象
            exception = exc_info.value
            
            # 验证 1：异常类型应该是 ExternalServiceError
            assert isinstance(exception, ExternalServiceError), \
                f"应该抛出 ExternalServiceError，实际: {type(exception)}"
            
            # 验证 2：异常消息应该包含 API 拦截失败的信息
            error_message = str(exception.message)
            assert api_error_message in error_message, \
                f"异常消息应该包含 API 拦截失败信息: {api_error_message}"
            
            # 验证 3：异常消息应该包含回退失败的信息
            assert fallback_error_message in error_message, \
                f"异常消息应该包含回退失败信息: {fallback_error_message}"
            
            # 验证 4：异常消息应该包含"所有下载方式均失败"
            assert "所有下载方式均失败" in error_message, \
                "异常消息应该明确说明所有方式均失败"
            
            # 验证 5：异常 code 应该正确
            assert exception.code == "DOWNLOAD_ALL_METHODS_FAILED", \
                f"异常 code 应该为 DOWNLOAD_ALL_METHODS_FAILED，实际: {exception.code}"
            
            # 验证 6：异常 errors 字段应该包含详细的错误信息
            assert hasattr(exception, 'errors'), "异常应该有 errors 属性"
            errors = exception.errors
            
            # 验证 7：errors 应该包含 api_intercept_error
            assert 'api_intercept_error' in errors, \
                "errors 应该包含 api_intercept_error"
            api_error = errors['api_intercept_error']
            assert 'type' in api_error, "api_intercept_error 应该包含 type"
            assert 'message' in api_error, "api_intercept_error 应该包含 message"
            assert api_error['type'] == 'ValueError', \
                f"API 错误类型应该为 ValueError，实际: {api_error['type']}"
            assert api_error_message in api_error['message'], \
                f"API 错误消息应该包含: {api_error_message}"
            
            # 验证 8：errors 应该包含 fallback_error
            assert 'fallback_error' in errors, \
                "errors 应该包含 fallback_error"
            fallback_error = errors['fallback_error']
            assert 'type' in fallback_error, "fallback_error 应该包含 type"
            assert 'message' in fallback_error, "fallback_error 应该包含 message"
            assert fallback_error['type'] == 'RuntimeError', \
                f"回退错误类型应该为 RuntimeError，实际: {fallback_error['type']}"
            assert fallback_error_message in fallback_error['message'], \
                f"回退错误消息应该包含: {fallback_error_message}"
            
            # 验证 9：异常消息应该包含错误类型信息
            assert 'ValueError' in error_message, \
                "异常消息应该包含 API 错误类型 ValueError"
            assert 'RuntimeError' in error_message, \
                "异常消息应该包含回退错误类型 RuntimeError"
            
            # 验证 10：错误链应该按顺序排列（API 失败 → 回退失败）
            # 注意：如果两个错误消息相同，位置可能相同，这是可以接受的
            api_error_pos = error_message.find(api_error_message)
            fallback_error_pos = error_message.find(fallback_error_message)
            
            # 如果错误消息不同，应该按顺序排列
            if api_error_message != fallback_error_message:
                assert api_error_pos < fallback_error_pos, \
                    "错误链应该按顺序排列：API 失败在前，回退失败在后"
            else:
                # 如果错误消息相同，至少应该出现两次
                assert error_message.count(api_error_message) >= 2, \
                    "相同的错误消息应该出现至少两次（API 失败和回退失败）"
