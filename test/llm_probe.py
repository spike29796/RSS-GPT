"""Probe the production LLM endpoint with the exact gpt_summary prompt.

Answers, with one real call:
- how long a single summary call takes (elapsed seconds)
- how many tokens it actually bills (prompt / completion / reasoning if any)

Run with the same env the Actions workflow uses:
  OPENAI_API_KEY=... OPENAI_BASE_URL=... CUSTOM_MODEL=... python test/llm_probe.py

No data leaves your machine except the single API call itself.
"""
import os
import time

from openai import OpenAI

ARTICLE = (
    "OpenAI 今日发布了一项新的模型更新，介绍了在推理效率方面的改进。"
    "官方称新模型在保持质量的前提下降低了延迟，并面向开发者逐步开放。"
    "本次更新还包含若干安全修复。\n"
) * 5  # ~几百字，和线上截断后的典型输入相当

categories = ["模型发布", "行业动态", "政策法规", "开源项目", "产品应用"]
instruction = (
    "请用中文为这篇文章写一句话导读并翻译标题，严格按照以下格式输出：第一行只输出一个分类，"
    f"必须从以下分类中选择一个：{'、'.join(categories)}，除此之外第一行不要输出任何其他内容；"
    "第二行用中文写一句话导读，不超过50字，必须是一句话，不要分点、不要编号，并按照以下格式输出"
    "'<br><br>总结:'，<br>是HTML的换行符，输出时必须保留2个，并且必须在'总结:'二字之前；"
    "第三行只输出文章标题的中文翻译，除此之外第三行不要输出任何其他内容"
)

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
model = os.environ.get("CUSTOM_MODEL", "gpt-4o-mini")

print(f"endpoint: {client.base_url}  model: {model}")
started = time.time()
completion = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"测试文章标题\n{ARTICLE}"},
    ],
    timeout=300,
)
elapsed = time.time() - started

print(f"elapsed: {elapsed:.1f}s")
print(f"usage:   {completion.usage}")
print("--- model output ---")
print(completion.choices[0].message.content)
