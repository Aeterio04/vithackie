"""In-memory fake implementations for tests (offline execution)."""

from typing import Any, Dict, List, Optional, Tuple
from kawach_fix.clients.github import GitHubClient, GitHubClientError
from kawach_fix.clients.llm import LLMClient
from kawach_fix.clients.runner import ScriptRunner
from kawach_fix.schemas import PullRequestInfo, RunItem


class FakeRunner(ScriptRunner):
    """Fake Playwright test runner with deterministic canned outcomes."""

    def __init__(self, outcomes: Optional[List[RunItem]] = None):
        self.outcomes = list(outcomes or [])
        self.call_count = 0
        self.recorded_calls: List[Dict[str, Any]] = []

    async def run_test(
        self,
        script_path_or_code: str,
        target_url: str,
        project_dir: str,
        timeout_sec: int,
        run_index: int = 1,
    ) -> RunItem:
        self.recorded_calls.append({
            "script": script_path_or_code,
            "target_url": target_url,
            "project_dir": project_dir,
            "timeout_sec": timeout_sec,
            "run_index": run_index,
        })
        self.call_count += 1
        if self.outcomes:
            # Pop or wrap around
            idx = (self.call_count - 1) % len(self.outcomes)
            return self.outcomes[idx]
        return RunItem(index=run_index, passed=True, duration_ms=50)


class FakeGitHub(GitHubClient):
    """In-memory Fake GitHub Client matching GitHubClient protocol."""

    def __init__(
        self,
        latest_commit: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Tuple[str, str]]] = None,
        existing_prs: Optional[List[PullRequestInfo]] = None,
        error_to_raise: Optional[GitHubClientError] = None,
    ):
        self.latest_commit = latest_commit or {
            "sha": "1234567890abcdef1234567890abcdef12345678",
            "message": "feat: update button component",
            "author": "Alice Tester",
            "files": [
                {
                    "filename": "src/components/Counter.tsx",
                    "status": "modified",
                    "patch": "@@ -5,3 +5,3 @@\n-  setCount(c => c + 1);\n+  setCount(c => c);\n",
                }
            ],
        }
        self.files = dict(files or {
            "src/components/Counter.tsx": (
                "export function Counter() {\n  const [count, setCount] = useState(0);\n  const onClick = () => {\n    setCount(c => c);\n  };\n  return <button id='add' onClick={onClick}>Add</button>;\n}",
                "blob_sha_counter_111",
            )
        })
        self.branches: Dict[str, str] = {}
        self.prs: List[PullRequestInfo] = list(existing_prs or [])
        self.updated_files: List[Dict[str, Any]] = []
        self.created_refs: List[Tuple[str, str, str]] = []
        self.error_to_raise = error_to_raise
        self.recorded_calls: List[str] = []

    async def get_latest_main_commit(self, repo: str) -> Dict[str, Any]:
        self.recorded_calls.append(f"get_latest_main_commit({repo})")
        if self.error_to_raise:
            raise self.error_to_raise
        return self.latest_commit

    async def get_file_content(self, repo: str, path: str, ref: str) -> Tuple[str, str]:
        self.recorded_calls.append(f"get_file_content({repo}, {path}, {ref})")
        if self.error_to_raise:
            raise self.error_to_raise
        if path in self.files:
            return self.files[path]
        raise GitHubClientError(404, f"File {path} not found")

    async def get_ref(self, repo: str, branch_name: str) -> Optional[str]:
        self.recorded_calls.append(f"get_ref({repo}, {branch_name})")
        if self.error_to_raise:
            raise self.error_to_raise
        return self.branches.get(branch_name)

    async def create_ref(self, repo: str, branch_name: str, sha: str) -> None:
        self.recorded_calls.append(f"create_ref({repo}, {branch_name}, {sha})")
        if self.error_to_raise:
            raise self.error_to_raise
        self.branches[branch_name] = sha
        self.created_refs.append((repo, branch_name, sha))

    async def update_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        blob_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.recorded_calls.append(f"update_file({repo}, {path}, {branch})")
        if self.error_to_raise:
            raise self.error_to_raise
        record = {
            "repo": repo,
            "path": path,
            "content": content,
            "message": message,
            "branch": branch,
            "blob_sha": blob_sha,
        }
        self.updated_files.append(record)
        new_blob = f"blob_sha_{len(self.updated_files)}"
        self.files[path] = (content, new_blob)
        return {"content": {"sha": new_blob}}

    async def find_existing_pr(
        self, repo: str, head_branch: str, base_branch: str = "main"
    ) -> Optional[PullRequestInfo]:
        self.recorded_calls.append(f"find_existing_pr({repo}, {head_branch}, {base_branch})")
        if self.error_to_raise:
            raise self.error_to_raise
        for pr in self.prs:
            if pr.branch == head_branch:
                return pr
        return None

    async def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> PullRequestInfo:
        self.recorded_calls.append(f"create_pr({repo}, {head_branch})")
        if self.error_to_raise:
            raise self.error_to_raise
        pr_number = len(self.prs) + 1
        new_pr = PullRequestInfo(
            number=pr_number,
            url=f"https://github.com/{repo}/pull/{pr_number}",
            branch=head_branch,
            created=True,
        )
        self.prs.append(new_pr)
        return new_pr


class FakeLLM(LLMClient):
    """Fake LLM returning canned responses, with support for consecutive responses."""

    def __init__(self, responses: Optional[List[str]] = None):
        self.responses = list(responses or [])
        self.call_count = 0
        self.recorded_calls: List[Dict[str, Any]] = []

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        self.recorded_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
        })
        self.call_count += 1
        if self.responses:
            idx = min(self.call_count - 1, len(self.responses) - 1)
            return self.responses[idx]
        return "{}"
