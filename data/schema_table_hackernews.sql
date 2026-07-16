-- Schema cho Hacker News crawler
-- Hacker News không cần session/cookie/login, nên bỏ bảng tiktok_sessions.
-- Hacker News không có views/likes/shares/bookmarks; score và descendants/comment_count nằm trong bảng metrics.

PRAGMA foreign_keys = ON;

-- Nguồn Hacker News cần theo dõi
-- source_type:
--   topstories/newstories/beststories/askstories/showstories/jobstories: lấy từ Firebase API
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,

    -- Theo tab / nhóm dữ liệu của Hacker News
    -- news  -> topstories.json
    -- newest -> newstories.json
    -- best  -> beststories.json
    -- ask   -> askstories.json
    -- show  -> showstories.json
    -- jobs  -> jobstories.json
    source_type VARCHAR(30) NOT NULL UNIQUE,

    -- Chỉ lưu path, không lưu full URL
    -- Full URL = HACKERNEWS_BASE_URL + '/' + api_path
    api_path VARCHAR(100) NOT NULL UNIQUE,

    is_active BOOLEAN DEFAULT 1,
    is_accessible BOOLEAN DEFAULT 1,

    include_comments BOOLEAN DEFAULT 0,
    comment_max_depth INTEGER DEFAULT 2,
    max_days_old INTEGER DEFAULT 3,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER DEFAULT NULL,
    schedule_override_minutes INTEGER DEFAULT NULL,

    CONSTRAINT ck_hn_source_type CHECK (
        source_type IN (
            'news',
            'newest',
            'best',
            'ask',
            'show',
            'jobs'
        )
    ),

    CONSTRAINT ck_hn_api_path CHECK (
        api_path IN (
            'topstories.json',
            'newstories.json',
            'beststories.json',
            'askstories.json',
            'showstories.json',
            'jobstories.json'
        )
    )
);

CREATE INDEX idx_sources_active ON sources (is_active);
CREATE INDEX idx_sources_accessible ON sources (is_accessible);
CREATE INDEX idx_sources_next_scrape ON sources (next_scrape);

-- Bài viết / job / poll trên Hacker News
-- hn_post_id chính là item.id từ Hacker News API
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    hn_post_id INTEGER NOT NULL,

    post_type VARCHAR(20) NOT NULL DEFAULT 'story'
        CHECK (post_type IN ('story', 'job', 'poll')),

    title TEXT,
    url TEXT,
    hn_item_url TEXT,
    author VARCHAR(100),

    posted_at DATETIME NOT NULL,          -- map từ time
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN DEFAULT 1,
    tracking_until DATETIME,
    is_deleted BOOLEAN DEFAULT 0,
    is_dead BOOLEAN DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,
    metric_tier VARCHAR(20) NOT NULL DEFAULT 'bootstrap',
    last_engagement_velocity FLOAT,
    cold_check_count INTEGER NOT NULL DEFAULT 0,
    metric_scan_miss_count INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX ix_posts_hn_post_id ON posts (hn_post_id);
CREATE INDEX idx_posts_posted_at ON posts (posted_at);
CREATE INDEX idx_posts_author ON posts (author);
CREATE INDEX idx_posts_metric_due ON posts (is_tracked, next_metric_update);
CREATE INDEX idx_posts_last_metric_update ON posts (last_metric_update);

-- Một post có thể xuất hiện ở nhiều source: newstories, topstories, beststories, keyword...
CREATE TABLE post_sources (
    post_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (post_id, source_id),
    FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE
);
CREATE INDEX idx_post_sources_source ON post_sources (source_id, last_seen_at);

-- Lịch sử metric của post theo thời gian
CREATE TABLE post_metrics (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,

    score INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,

    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE
);
CREATE INDEX idx_post_metrics_post_time ON post_metrics (post_id, recorded_at);
CREATE INDEX idx_post_metrics_recorded_at ON post_metrics (recorded_at);
CREATE INDEX idx_post_metrics_job_time ON post_metrics (job_id, recorded_at);

-- Bình luận Hacker News
-- hn_comment_id chính là item.id của comment
CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,                 -- story/job/poll gốc trong bảng posts
    parent_comment_id INTEGER,                -- comment cha nội bộ, nếu có

    hn_comment_id INTEGER NOT NULL,
    parent_hn_item_id INTEGER,                -- parent từ HN API, có thể là post hoặc comment

    author VARCHAR(100),
    comment_text TEXT,
    posted_at DATETIME,

    is_deleted BOOLEAN DEFAULT 0,
    is_dead BOOLEAN DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_json TEXT,

    FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES comments (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX ix_comments_hn_comment_id ON comments (hn_comment_id);
CREATE INDEX idx_comments_post ON comments (post_id);
CREATE INDEX idx_comments_parent_hn_item ON comments (parent_hn_item_id);
CREATE INDEX idx_comments_author ON comments (author);

-- Cache thống kê theo source/ngày
CREATE TABLE analytics_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    date DATETIME NOT NULL,

    total_posts INTEGER DEFAULT 0,
    total_score INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,

    avg_score_per_post FLOAT,
    avg_comments_per_post FLOAT,

    top_post_id INTEGER,
    growth_rate FLOAT,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_hn_analytics_cache UNIQUE (source_id, date),
    FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE,
    FOREIGN KEY (top_post_id) REFERENCES posts (id) ON DELETE SET NULL
);
CREATE INDEX idx_analytics_source_date ON analytics_cache (source_id, date);

-- Theo dõi pipeline crawl/update/analytics
CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scrape_posts'
        CHECK (job_type IN ('scrape_posts', 'scrape_new_posts', 'update_metrics', 'scrape_comments', 'analytics')),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    posts_found INTEGER NOT NULL DEFAULT 0,
    posts_new INTEGER NOT NULL DEFAULT 0,
    comments_found INTEGER NOT NULL DEFAULT 0,
    comments_new INTEGER NOT NULL DEFAULT 0,

    items_total INTEGER NOT NULL DEFAULT 0,
    items_updated INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME
);
CREATE INDEX idx_pipeline_jobs_source_time ON pipeline_jobs (source_id, started_at);
CREATE INDEX idx_pipeline_jobs_type_status ON pipeline_jobs (job_type, status, started_at);

-- Log lỗi cho từng pipeline job
CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,
    error_type VARCHAR(100),
    error_details TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_pipeline_logs_job ON pipeline_logs (job_id, created_at);
CREATE INDEX idx_pipeline_logs_source ON pipeline_logs (source_id, created_at);
CREATE INDEX idx_pipeline_logs_level ON pipeline_logs (log_level, created_at);
