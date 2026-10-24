"""GitHub API Client interface and httpx-based implementation."""

import base64
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable
import httpx
from pydantic import SecretStr

from kawach_fix.schemas import PullRequestInfo


class GitHubClientError(Exception):
    """Custom exception raised when GitHub REST API requests fail."""

    def __init__(self, status_code: int, message: str, is_rate_limit: bool = False):
        super().__init__(f"GitHub API error ({status_code}): {message}")
        self.status_code = status_code
        self.message = message
        self.is_rate_limit = is_rate_limit


@runtime_checkable
class GitHubClient(Protocol):
    """Protocol defining GitHub API interactions required by the fix pipeline."""

    async def get_latest_main_commit(self, repo: str) -> Dict[str, Any]:
        """Fetch the latest commit object on origin/main."""
        ...

    async def get_file_content(self, repo: str, path: str, ref: str) -> Tuple[str, str]:
        """Fetch decoded file content and blob_sha at a specific commit ref."""
        ...

    async def get_ref(self, repo: str, branch_name: str) -> Optional[str]:
        """Check if branch ref exists, returning target sha if present."""
        ...

    async def create_ref(self, repo: str, branch_name: str, sha: str) -> None:
        """Create a new branch pointing to the specified commit sha."""
        ...

    async def update_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        blob_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a file via the Contents API."""
        ...

    async def find_existing_pr(
        self, repo: str, head_branch: str, base_branch: str = "main"
    ) -> Optional[PullRequestInfo]:
        """Search for an existing open pull request with matching head and base branches."""
        ...

    async def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> PullRequestInfo:
        """Open a pull request into main."""
        ...


class HttpxGitHubClient:
    """Production GitHub client using httpx.AsyncClient with PAT authentication."""

    def __init__(self, token: Union[str, SecretStr], base_url: str = "https://api.github.com", client: Optional[httpx.AsyncClient] = None):
        self._token_str = token.get_secret_value() if isinstance(token, SecretStr) else token
        self._base_url = base_url.rstrip("/")
        self._client = client

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_str}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Kawach-Fix-Pipeline",
        }

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers = {**self._headers(), **kwargs.pop("headers", {})}

        if self._client:
            res = await self._client.request(method, url, headers=headers, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.request(method, url, headers=headers, **kwargs)

        if res.is_error:
            status = res.status_code
            is_rl = status in (403, 429) and ("rate limit" in res.text.lower() or res.headers.get("x-ratelimit-remaining") == "0")
            try:
                err_json = res.json()
                msg = err_json.get("message", res.text)
            except Exception:
                msg = res.text or res.reason_phrase
            raise GitHubClientError(status_code=status, message=msg, is_rate_limit=is_rl)

        return res

    async def get_latest_main_commit(self, repo: str) -> Dict[str, Any]:
        res = await self._request("GET", f"/repos/{repo}/commits/main")
        data = res.json()
        commit_info = data.get("commit", {})
        author_info = commit_info.get("author", {})
        author_name = author_info.get("name") or author_info.get("email") or "Unknown"

        return {
            "sha": data.get("sha", ""),
            "message": commit_info.get("message", ""),
            "author": author_name,
            "files": data.get("files", []),
        }

    async def get_file_content(self, repo: str, path: str, ref: str) -> Tuple[str, str]:
        res = await self._request("GET", f"/repos/{repo}/contents/{path}", params={"ref": ref})
        data = res.json()
        if not isinstance(data, dict):
            raise GitHubClientError(400, f"Path '{path}' is a directory or submodule, not a file.")

        blob_sha = data.get("sha", "")
        encoding = data.get("encoding")
        raw_content = data.get("content", "")

        if encoding == "base64" and raw_content:
            decoded = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            return decoded, blob_sha

        # Fallback to direct raw request if content wasn't inline
        raw_res = await self._request(
            "GET",
            f"/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        return raw_res.text, blob_sha

    async def get_ref(self, repo: str, branch_name: str) -> Optional[str]:
        ref_path = f"heads/{branch_name}"
        try:
            res = await self._request("GET", f"/repos/{repo}/git/ref/{ref_path}")
            data = res.json()
            return data.get("object", {}).get("sha")
        except GitHubClientError as e:
            if e.status_code == 404:
                return None
            raise

    async def create_ref(self, repo: str, branch_name: str, sha: str) -> None:
        payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
        await self._request("POST", f"/repos/{repo}/git/refs", json=payload)

    async def update_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        blob_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload: Dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if blob_sha:
            payload["sha"] = blob_sha

        res = await self._request("PUT", f"/repos/{repo}/contents/{path}", json=payload)
        return res.json()

    async def find_existing_pr(
        self, repo: str, head_branch: str, base_branch: str = "main"
    ) -> Optional[PullRequestInfo]:
        owner = repo.split("/")[0]
        params = {
            "state": "open",
            "head": f"{owner}:{head_branch}",
            "base": base_branch,
        }
        res = await self._request("GET", f"/repos/{repo}/pulls", params=params)
        prs = res.json()
        if isinstance(prs, list) and len(prs) > 0:
            item = prs[0]
            return PullRequestInfo(
                number=item.get("number"),
                url=item.get("html_url"),
                branch=head_branch,
                created=False,
            )
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
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
            "draft": draft,
        }
        res = await self._request("POST", f"/repos/{repo}/pulls", json=payload)
        data = res.json()
        return PullRequestInfo(
            number=data.get("number"),
            url=data.get("html_url"),
            branch=head_branch,
            created=True,
        )
