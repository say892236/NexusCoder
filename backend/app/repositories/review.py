"""Review 与 ReviewComment model 的数据访问 Repository。

封装 Review 创建、状态跟踪、条件查询、inline comment 与统计聚合，避免 API 和 task
直接散落 SQLAlchemy 查询逻辑。
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review, ReviewComment


class ReviewRepository:
    """Review model 的数据访问层。

    集中处理 PR Review 状态、条件过滤，以及携带关联 comment 的完整查询。
    """

    @staticmethod
    async def get_by_id(db: AsyncSession, review_id: UUID | str) -> Review | None:
        """按 UUID 查询 Review。

        Args:
            db: Database session
            review_id: Review UUID

        Returns:
            Review object if found, None otherwise
        """
        result = await db.execute(select(Review).where(Review.id == review_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_pr(db: AsyncSession, repository: str, pr_number: int) -> list[Review]:
        """查询指定 PR 的全部 Review。

        PR 每次更新都可能触发新 Review，因此按最新创建时间倒序返回。

        Args:
            db: Database session
            repository: Repository in format 'owner/repo'
            pr_number: Pull request number

        Returns:
            List of Review objects ordered by created_at DESC
        """
        result = await db.execute(
            select(Review)
            .where(and_(Review.repository == repository, Review.pr_number == pr_number))
            .order_by(Review.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_installation(
        db: AsyncSession,
        installation_id: UUID | str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Review]:
        """分页查询 Installation 的 Review，可按状态过滤。

        Args:
            db: Database session
            installation_id: Installation UUID
            status: Optional status filter (PENDING, PROCESSING, COMPLETED, FAILED)
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return

        Returns:
            List of Review objects ordered by created_at DESC
        """
        query = select(Review).where(Review.installation_id == installation_id)

        if status:
            query = query.where(Review.status == status)

        query = query.order_by(Review.created_at.desc()).offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        installation_id: UUID | str,
        pr_number: int,
        repository: str,
        commit_sha: str,
        metadata: dict | None = None,
    ) -> Review:
        """创建 PENDING 状态的 Review。

        Args:
            db: Database session
            installation_id: Installation UUID
            pr_number: Pull request number
            repository: Repository in format 'owner/repo'
            commit_sha: Git commit SHA being reviewed
            metadata: Optional PR metadata (title, author, etc.)

        Returns:
            Created Review object
        """
        review = Review(
            installation_id=installation_id,
            pr_number=pr_number,
            repository=repository,
            commit_sha=commit_sha,
            pr_metadata=metadata or {},
            status="PENDING",
        )

        db.add(review)
        await db.flush()
        await db.refresh(review)

        return review

    @staticmethod
    async def update_status(
        db: AsyncSession,
        review: Review,
        status: str,
        error: str | None = None,
    ) -> Review:
        """更新 Review 状态及对应时间戳。

        状态进入 PROCESSING 时设置 started_at，进入 COMPLETED 或 FAILED 时设置 completed_at。

        Args:
            db: Database session
            review: Review object to update
            status: New status (PENDING, PROCESSING, COMPLETED, FAILED)
            error: Error message if status is FAILED

        Returns:
            Updated Review object
        """
        old_status = review.status
        review.status = status

        # 根据生命周期状态维护开始和完成时间。
        if status == "PROCESSING" and old_status == "PENDING":
            review.started_at = datetime.now(timezone.utc)

        if status in ["COMPLETED", "FAILED"]:
            review.completed_at = datetime.now(timezone.utc)

        if error:
            review.error = error

        await db.flush()
        await db.refresh(review)

        return review

    @staticmethod
    async def add_review_text(db: AsyncSession, review: Review, review_text: str) -> Review:
        """保存 AI Agent 生成的 Review summary。

        Args:
            db: Database session
            review: Review object to update
            review_text: Overall review summary from AI

        Returns:
            Updated Review object
        """
        review.review_text = review_text

        await db.flush()
        await db.refresh(review)

        return review

    @staticmethod
    async def get_pending_reviews(db: AsyncSession, limit: int = 10) -> list[Review]:
        """按创建时间查询待处理的 PENDING Review。

        供后台 worker 获取需要处理的 Review。

        Args:
            db: Database session
            limit: Maximum number of reviews to return

        Returns:
            List of Review objects with status=PENDING
        """
        result = await db.execute(
            select(Review)
            .where(Review.status == "PENDING")
            .order_by(Review.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_pending_review(
        db: AsyncSession,
        installation_id: UUID | str,
        repository: str,
        pr_number: int,
        commit_sha: str,
        pr_metadata: dict,
        celery_task_id: str,
    ) -> Review:
        """创建带 Celery task ID 的 PENDING Review。

        webhook handler 在异步 task 入队前使用，避免 worker 查询不到记录。

        Args:
            db: Database session
            installation_id: Installation UUID
            repository: Repository in format 'owner/repo'
            pr_number: Pull request number
            commit_sha: Git commit SHA being reviewed
            pr_metadata: PR metadata (title, author, url, etc.)
            celery_task_id: Celery task ID for tracking

        Returns:
            Created Review object with PENDING status
        """
        review = Review(
            installation_id=installation_id,
            repository=repository,
            pr_number=pr_number,
            commit_sha=commit_sha,
            pr_metadata=pr_metadata,
            status="PENDING",
            celery_task_id=celery_task_id,
        )

        db.add(review)
        await db.flush()
        await db.refresh(review)

        return review


class ReviewCommentRepository:
    """ReviewComment model 的数据访问层。

    封装独立评论的创建、按文件或严重级别查询，以及 GitHub 发布状态管理。
    """

    @staticmethod
    async def create(
        db: AsyncSession,
        review_id: UUID | str,
        title: str,
        file_path: str,
        line_number: int,
        comment_text: str,
        severity: str,
        category: str,
        line_end: int | None = None,
    ) -> ReviewComment:
        """创建新的 ReviewComment。

        Args:
            db: Database session
            review_id: Review UUID this comment belongs to
            title: Short finding title
            file_path: Path to file (e.g., 'src/main.py')
            line_number: Starting line number
            comment_text: The actual comment message
            severity: INFO, WARNING, ERROR, or CRITICAL
            category: BUG, SECURITY, PERFORMANCE, etc.
            line_end: Ending line number for multi-line comments

        Returns:
            Created ReviewComment object
        """
        comment = ReviewComment(
            review_id=review_id,
            title=title,
            file_path=file_path,
            line_number=line_number,
            line_end=line_end,
            comment_text=comment_text,
            severity=severity,
            category=category,
        )

        db.add(comment)
        await db.flush()
        await db.refresh(comment)

        return comment

    @staticmethod
    async def get_by_review(db: AsyncSession, review_id: UUID | str) -> list[ReviewComment]:
        """查询 Review 的全部 comment。

        Args:
            db: Database session
            review_id: Review UUID

        Returns:
            List of ReviewComment objects ordered by file_path, then line_number
        """
        result = await db.execute(
            select(ReviewComment)
            .where(ReviewComment.review_id == review_id)
            .order_by(ReviewComment.file_path, ReviewComment.line_number)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_severity(
        db: AsyncSession, review_id: UUID | str, severity: str
    ) -> list[ReviewComment]:
        """按严重级别过滤 ReviewComment。

        Args:
            db: Database session
            review_id: Review UUID
            severity: Severity level (INFO, WARNING, ERROR, CRITICAL)

        Returns:
            List of ReviewComment objects with matching severity
        """
        result = await db.execute(
            select(ReviewComment).where(
                and_(
                    ReviewComment.review_id == review_id,
                    ReviewComment.severity == severity,
                )
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_posted(
        db: AsyncSession, comment: ReviewComment, github_comment_id: int
    ) -> ReviewComment:
        """标记 comment 已成功发布到 GitHub。

        GitHub API 发布成功后保存其 comment ID。

        Args:
            db: Database session
            comment: ReviewComment object
            github_comment_id: GitHub API comment ID

        Returns:
            Updated ReviewComment object
        """
        comment.github_comment_id = github_comment_id

        await db.flush()
        await db.refresh(comment)

        return comment

    @staticmethod
    async def count_by_severity(db: AsyncSession, review_id: UUID | str) -> dict[str, int]:
        """按严重级别统计 Review comment 数量。

        用于展示 Review 汇总统计。

        Args:
            db: Database session
            review_id: Review UUID

        Returns:
            Dict mapping severity to count: {'CRITICAL': 2, 'ERROR': 5, ...}
        """
        result = await db.execute(
            select(ReviewComment.severity, func.count(ReviewComment.id))
            .where(ReviewComment.review_id == review_id)
            .group_by(ReviewComment.severity)
        )

        counts: dict[str, int] = {row[0]: row[1] for row in result.all()}
        return counts
