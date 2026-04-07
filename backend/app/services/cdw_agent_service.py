import json
import os
import shlex
import subprocess
from typing import Any
import httpx
from app.core.config import get_settings
from app.core.exceptions import AppError

settings = get_settings()


class CDWAgentService:
    @staticmethod
    def _extract_json_array(raw: str) -> list[dict[str, Any]]:
        raw = raw.strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get('items'), list):
                return data['items']
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1 and end > start:
            chunk = raw[start : end + 1]
            try:
                data = json.loads(chunk)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        raise AppError('CDW agent returned invalid JSON payload', 502)

    @staticmethod
    def _run_script(query: str, limit: int) -> list[dict[str, Any]]:
        command = settings.cdw_agent_command.strip()
        if not command:
            raise AppError('CDW_AGENT_COMMAND is not configured', 500)

        env = dict(os.environ)
        env['CDW_QUERY'] = query
        env['CDW_LIMIT'] = str(limit)

        completed = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=settings.cdw_agent_timeout_seconds,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise AppError(f'CDW agent failed: {completed.stderr.strip() or "unknown error"}', 502)
        return CDWAgentService._extract_json_array(completed.stdout)

    @staticmethod
    def _run_openai(query: str, limit: int) -> list[dict[str, Any]]:
        api_key = settings.openai_api_key.strip()
        if not api_key:
            raise AppError('OPENAI_API_KEY is not configured', 500)

        model = settings.cdw_openai_model
        instruction = (
            'Return only valid JSON array. Include up to {limit} router products with keys: '
            'sku,name,brand,model,price,currency,availability,description,ports,wifi_standard,specs. '
            'price must be numeric.'
        ).format(limit=limit)

        payload = {
            'model': model,
            'input': [
                {
                    'role': 'system',
                    'content': [
                        {
                            'type': 'input_text',
                            'text': (
                                'You are a CDW router extraction agent. Return strict JSON only with real or likely business router catalog rows.'
                            ),
                        }
                    ],
                },
                {'role': 'user', 'content': [{'type': 'input_text', 'text': f'{instruction}\nUser query: {query}'}]},
            ],
            'temperature': 0.1,
            'max_output_tokens': 3000,
        }

        with httpx.Client(timeout=60) as client:
            response = client.post(
                'https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json=payload,
            )
        if response.status_code >= 400:
            raise AppError(f'OpenAI request failed: {response.text}', 502)

        data = response.json()
        text_parts: list[str] = []
        for item in data.get('output', []):
            for content in item.get('content', []):
                if content.get('type') in {'output_text', 'text'} and content.get('text'):
                    text_parts.append(content['text'])
        joined = '\n'.join(text_parts).strip()
        if not joined:
            joined = data.get('output_text', '')
        return CDWAgentService._extract_json_array(joined)

    @staticmethod
    def fetch_routers(query: str, limit: int) -> list[dict[str, Any]]:
        mode = settings.cdw_ingest_mode.strip().lower()
        if mode == 'openai':
            return CDWAgentService._run_openai(query, limit)
        return CDWAgentService._run_script(query, limit)
