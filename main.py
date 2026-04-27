import ast
import os
import re

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from github import Github, Auth
from pydantic import BaseModel
from starlette.datastructures import URL
from starlette.middleware.cors import CORSMiddleware
from pathlib import Path

app = FastAPI()
load_dotenv(dotenv_path=".env")

api_key = os.getenv("GITHUB_TOKEN")

g = Github(auth=Auth.Token(str(api_key)))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/get_project")
async def get_project(projectURL: str):
    dd: URL = URL(projectURL)
    repo = g.get_repo(dd.path[1:])
    content = repo.get_contents("")
    result = {repo.name: []}
    while content:
        file_content = content.pop(0)
        if not os.path.exists(f"{repo.name}/"):
            os.mkdir(f"{repo.name}/")
        if file_content.type == "dir":
            content.extend(repo.get_contents(file_content.path))
        elif file_content.name.endswith((".java", ".py", ".c", ".cpp", ".h")):
            with open(f"{repo.name}/"+file_content.name+".txt", "w", encoding="UTF-8") as f:
                f.write(file_content.decoded_content.decode())
                result[repo.name].append(file_content.name+".txt")
    g.close()
    return result

@app.get("/projects/get_file_contents")
async def get_file_contents(project:str, fileName: str):
    contents = "" #there has to be a better way to do this
    with open(f"{project}/{fileName}", "rb") as f:
        contents = f.read()
    return {"result": contents}


class FunctionInfo(BaseModel):
    function_name: str
    start_line: int
    end_line: int
    code: str
    explanation: str


class FileResponse(BaseModel):
    result: list[FunctionInfo]


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "codellama"
MAX_EXPLANATION_LENGTH = 500


def extract_functions(file_content: str, file_extension: str = ".py") -> list[dict]:
    if file_extension == ".py":
        return extract_python_functions(file_content)
    elif file_extension in [".js", ".ts"]:
        return extract_js_functions(file_content)
    elif file_extension in [".java", ".cpp", ".c"]:
        return extract_c_functions(file_content)
    else:
        return extract_generic_functions(file_content)


def extract_python_functions(file_content: str) -> list[dict]:
    functions = []
    try:
        tree = ast.parse(file_content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "function_name": node.name,
                    "start_line": node.lineno,
                    "end_line": node.end_lineno or node.lineno,
                    "code": "\n".join(file_content.splitlines()[node.lineno - 1:node.end_lineno])
                })
    except SyntaxError:
        functions = extract_generic_functions(file_content)
    return functions


def extract_js_functions(file_content: str) -> list[dict]:
    functions = []
    lines = file_content.splitlines()

    pattern = r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\('

    i = 0
    while i < len(lines):
        match = re.match(pattern, lines[i])
        if match:
            func_name = match.group(1)
            start_line = i + 1

            brace_count = 0
            j = i
            found_start = False

            while j < len(lines):
                if '{' in lines[j]:
                    brace_count += lines[j].count('{')
                    found_start = True
                if '}' in lines[j]:
                    brace_count -= lines[j].count('}')
                if found_start and brace_count == 0:
                    break
                j += 1

            end_line = j + 1
            code = "\n".join(lines[i:end_line])

            functions.append({
                "function_name": func_name,
                "start_line": start_line,
                "end_line": end_line,
                "code": code
            })
            i = end_line
        else:
            i += 1

    return functions


def extract_c_functions(file_content: str) -> list[dict]:
    functions = []
    lines = file_content.splitlines()

    pattern = r'^\s*(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\('

    i = 0
    while i < len(lines):
        match = re.match(pattern, lines[i])
        if match:
            func_name = match.group(1)
            start_line = i + 1

            brace_count = 0
            j = i
            found_start = False

            while j < len(lines):
                if '{' in lines[j]:
                    brace_count += lines[j].count('{')
                    found_start = True
                if '}' in lines[j]:
                    brace_count -= lines[j].count('}')
                if found_start and brace_count == 0:
                    break
                j += 1

            end_line = j + 1
            code = "\n".join(lines[i:end_line])

            functions.append({
                "function_name": func_name,
                "start_line": start_line,
                "end_line": end_line,
                "code": code
            })
            i = end_line
        else:
            i += 1

    return functions


def extract_generic_functions(file_content: str) -> list[dict]:
    functions = []
    lines = file_content.splitlines()

    patterns = [
        r'^\s*(?:def|function|func|sub)\s+(\w+)\s*\(',
        r'^\s*(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(',
    ]

    i = 0
    while i < len(lines):
        for pattern in patterns:
            match = re.match(pattern, lines[i])
            if match:
                func_name = match.group(1)
                start_line = i + 1

                brace_count = 0
                j = i
                found_start = False

                while j < len(lines):
                    if '{' in lines[j]:
                        brace_count += lines[j].count('{')
                        found_start = True
                    if '}' in lines[j]:
                        brace_count -= lines[j].count('}')
                    if found_start and brace_count == 0:
                        break
                    if not found_start and ':' in lines[j] and j > i:
                        break
                    j += 1

                end_line = j + 1
                code = "\n".join(lines[i:end_line])

                functions.append({
                    "function_name": func_name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "code": code
                })
                i = end_line
                break
        else:
            i += 1

    return functions


def truncate_code(code: str, max_length: int = 2000) -> str:
    if len(code) > max_length:
        lines = code.splitlines()
        truncated = "\n".join(lines[:50])
        return truncated + "\n... (код обрезан)"
    return code


def get_explanation_from_ollama(function_name: str, code: str) -> str:
    truncated_code = truncate_code(code, 1500)

    prompt = f"""Объясни функцию '{function_name}' на русском языке. 
    Опиши кратко (максимум ТОЛЬКО 100 символов на объяснение):
    - Что делает функция
    Код:
{truncated_code}
Объяснение:"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 150,
                    "temperature": 0.3
                }
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            explanation = result.get("response", "").strip()

            if len(explanation) > MAX_EXPLANATION_LENGTH:
                explanation = explanation[:MAX_EXPLANATION_LENGTH] + "..."

            return explanation
        else:
            return f"Ошибка Ollama: {response.status_code}"

    except requests.exceptions.Timeout:
        return "Превышено время ожидания"
    except requests.exceptions.ConnectionError:
        return "Ollama не запущен"


@app.get("/projects/get_contents_described")
async def get_contents_described(
        project: str = Query(..., description="Название проекта"),
        fileName: str = Query(..., description="Имя файла")
):
    """
    Возвращает полное содержимое файла и аннотированные функции
    """

    file_path = Path(f"./{project}/{fileName}")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Файл не найден: {file_path}")

    try:
        # Читаем полное содержимое файла
        with open(file_path, 'r', encoding='utf-8') as f:
            full_content = f.read()

        # Определяем расширение
        file_extension = Path(fileName).suffix

        # Извлекаем функции
        functions = extract_functions(full_content, file_extension)

        # Получаем объяснения для каждой функции
        result_functions = []
        for func in functions:
            explanation = get_explanation_from_ollama(
                func["function_name"],
                func["code"]
            )

            result_functions.append({
                "function_name": func["function_name"],
                "start_line": func["start_line"],
                "end_line": func["end_line"],
                "code": func["code"],
                "explanation": explanation
            })

        # Возвращаем полное содержимое и аннотации
        return {
            "full_content": full_content,
            "functions": result_functions,
            "result": result_functions  # Для обратной совместимости
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")