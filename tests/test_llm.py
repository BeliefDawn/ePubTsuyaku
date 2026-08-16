import threading
import unittest

from translator.llm import (
    SAKURA_HISTORY_LIMIT,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    SakuraLLMClient,
    TranslationHistory,
    _extract_translation_map,
    _parse_json_from_text,
)


class TranslationPayloadTests(unittest.TestCase):
    def test_parse_json_from_text_tolerates_trailing_garbage_after_object(self):
        payload = _parse_json_from_text('{"ok": true} trailing noise')

        self.assertEqual(payload, {"ok": True})

    def test_extract_translation_map_supports_keyed_object(self):
        payload = {"translations": {"seg_0001": "第一句", "seg_0002": "第二句"}}

        translation_map = _extract_translation_map(payload)

        self.assertEqual(translation_map["seg_0001"], "第一句")
        self.assertEqual(translation_map["seg_0002"], "第二句")

    def test_translate_repairs_missing_segments_with_followup_request(self):
        client = OpenAICompatibleLLMClient(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="demo-model",
        )
        responses = iter(
            [
                {"translations": {"seg_0001": "第一句"}},
                {"translations": {"seg_0002": "第二句"}},
            ]
        )
        requested_tool_names = []

        def fake_call_json(
            system_prompt,
            user_prompt,
            model,
            temperature,
            max_tokens=None,
            schema=None,
            tool_name="return_json",
            tool_description="",
        ):
            requested_tool_names.append(tool_name)
            return next(responses)

        client._call_json = fake_call_json  # type: ignore[method-assign]

        result = client.translate(
            book_metadata={"title": "Demo", "author": "Tester", "identifier": "demo", "language": "ja"},
            story_state={},
            segments=[
                {"id": "seg_0001", "text": "太郎は学校へ行った。"},
                {"id": "seg_0002", "text": "花子に会った。"},
            ],
            source_language="日语",
            target_language="中文",
        )

        self.assertEqual(
            result,
            {
                "seg_0001": "第一句",
                "seg_0002": "第二句",
            },
        )
        self.assertEqual(requested_tool_names, ["return_translations", "return_translations"])

    def test_mock_translate_titles_prefixes_each_title(self):
        client = MockLLMClient()

        self.assertEqual(client.translate_titles(["a", "b"]), ["[translated] a", "[translated] b"])
        self.assertEqual(client.translate_titles([]), [])

    def test_openai_translate_titles_falls_back_to_original_when_lines_short(self):
        client = OpenAICompatibleLLMClient(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="demo-model",
        )

        def fake_complete(messages, model, temperature, max_tokens=None, response_format=None):
            return "只翻译了第一行"

        client._complete = fake_complete  # type: ignore[method-assign]

        result = client.translate_titles(["标题A", "标题B"])

        self.assertEqual(result, ["只翻译了第一行", "标题B"])

    def test_sakura_delegates_context_phases_to_assistant(self):
        calls = {"summary": 0, "review": 0, "reference": 0}

        class FakeAssistant:
            def summarize(self, **kwargs):
                calls["summary"] += 1
                return {"chapter_summary": "x", "characters": []}

            def review(self, **kwargs):
                calls["review"] += 1
                return {"score": 90, "corrected_segments": {}}

            def extract_reference_patch(self, **kwargs):
                calls["reference"] += 1
                return {"series_notes": []}

        client = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
            assistant_client=FakeAssistant(),  # type: ignore[arg-type]
        )

        self.assertEqual(client.summarize({}, {}, [], "日语", "中文")["chapter_summary"], "x")
        self.assertEqual(client.review({}, {}, [], [], "日语", "中文")["score"], 90)
        self.assertEqual(client.extract_reference_patch({}, {}, [], "中文")["series_notes"], [])
        self.assertEqual(calls, {"summary": 1, "review": 1, "reference": 1})

    def test_sakura_without_assistant_keeps_noop_context_phases(self):
        client = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
        )

        summary = client.summarize({}, {}, [], "日语", "中文")
        self.assertEqual(summary["characters"], [])

        review = client.review({}, {}, [], [], "日语", "中文")
        self.assertEqual(review["score"], 100)

        reference = client.extract_reference_patch({}, {}, [], "中文")
        self.assertEqual(reference["terms"], [])

    def test_sakura_translate_injects_summary_glossary_into_prompt(self):
        client = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
        )
        captured = {}

        def fake_request(user_prompt, max_tokens):
            captured["prompt"] = user_prompt
            return "译文。"

        client._request = fake_request  # type: ignore[method-assign]

        client.translate(
            book_metadata={},
            story_state={
                "glossary": [{"source": "浮き輪", "target": "浮力环", "note": "泳具"}],
            },
            segments=[{"id": "seg_0001", "text": "浮き輪をつけている。"}],
            source_language="日语",
            target_language="中文",
        )

        self.assertIn("浮き輪->浮力环 #泳具", captured["prompt"])

    def test_sakura_shared_translation_context_reuses_history_across_clients(self):
        shared = TranslationHistory()
        client_a = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
            translation_history=shared,
        )
        client_b = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
            translation_history=shared,
        )
        captured = {}

        client_a._request = lambda user_prompt, max_tokens: "前一批译文。"  # type: ignore[method-assign]

        def fake_request_b(user_prompt, max_tokens):
            captured["prompt"] = user_prompt
            return "后一批译文。"

        client_b._request = fake_request_b  # type: ignore[method-assign]

        client_a.translate(
            book_metadata={},
            story_state={},
            segments=[{"id": "seg_0001", "text": "前文。"}],
            source_language="日语",
            target_language="中文",
        )
        client_b.translate(
            book_metadata={},
            story_state={},
            segments=[{"id": "seg_0002", "text": "后文。"}],
            source_language="日语",
            target_language="中文",
        )

        self.assertIn("前一批译文。", captured["prompt"])
        self.assertEqual(shared.read_history(SAKURA_HISTORY_LIMIT), ["后一批译文。"])
        self.assertEqual(client_a._history, [])
        self.assertEqual(client_b._history, [])

    def test_sakura_shared_translation_context_concurrent_read_write_is_safe(self):
        shared = TranslationHistory()

        def run_client(rounds: int) -> None:
            client = SakuraLLMClient(
                api_key="key",
                base_url="http://localhost:8080/v1",
                model="model",
                translation_history=shared,
            )
            client._request = lambda user_prompt, max_tokens: "译文。"  # type: ignore[method-assign]
            for i in range(rounds):
                client.translate(
                    book_metadata={},
                    story_state={},
                    segments=[{"id": f"seg_{i}", "text": f"文本{i}。"}],
                    source_language="日语",
                    target_language="中文",
                )

        threads = [threading.Thread(target=run_client, args=(20,)) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(shared.read_history(100)), 1)

    def test_sakura_without_shared_context_keeps_private_history(self):
        client_a = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
        )
        client_b = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
        )

        client_a._request = lambda user_prompt, max_tokens: "A译文。"  # type: ignore[method-assign]
        client_b._request = lambda user_prompt, max_tokens: "B译文。"  # type: ignore[method-assign]

        client_a.translate(
            book_metadata={},
            story_state={},
            segments=[{"id": "seg_0001", "text": "A文。"}],
            source_language="日语",
            target_language="中文",
        )
        client_b.translate(
            book_metadata={},
            story_state={},
            segments=[{"id": "seg_0002", "text": "B文。"}],
            source_language="日语",
            target_language="中文",
        )

        self.assertEqual(client_a._history, ["A译文。"])
        self.assertEqual(client_b._history, ["B译文。"])

    def test_sakura_request_raises_retryable_error_on_empty_choices(self):
        client = SakuraLLMClient(
            api_key="key",
            base_url="http://localhost:8080/v1",
            model="model",
        )

        class FakeResponse:
            choices = None

        client.client.chat.completions.create = lambda **kwargs: FakeResponse()  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError) as ctx:
            client._request("prompt", max_tokens=10)

        self.assertIn("未返回内容", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
