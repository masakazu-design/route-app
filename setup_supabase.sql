-- ========================================
-- 環境整備スケジュール作成システム - Supabase テーブル作成SQL
-- ========================================
-- Supabaseの「SQL Editor」でこのスクリプトを実行してください

-- ========================================
-- 1. 訪問先選択状態を保存するテーブル
-- ========================================
CREATE TABLE IF NOT EXISTS route_selections (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,  -- 保存名（例：「12月第2週」）
    selected_points JSONB NOT NULL,  -- 選択した訪問先のリスト
    num_days INTEGER DEFAULT 2,  -- 日数設定
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- 2. 計算結果を保存するテーブル
-- ========================================
CREATE TABLE IF NOT EXISTS route_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,  -- 保存名
    selection_id UUID REFERENCES route_selections(id) ON DELETE SET NULL,  -- 関連する選択状態
    day_routes JSONB NOT NULL,  -- 日別ルート（インデックスリスト）
    timetables JSONB,  -- タイムテーブルデータ
    calendar_texts JSONB,  -- カレンダー用テキスト
    selected_df JSONB NOT NULL,  -- 訪問先データ
    num_days INTEGER NOT NULL,
    optimize_mode VARCHAR(20) DEFAULT 'distance',  -- 最適化モード
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- 3. 実行履歴を保存するテーブル
-- ========================================
CREATE TABLE IF NOT EXISTS route_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    execution_date DATE NOT NULL,  -- 実行日
    result_id UUID REFERENCES route_results(id) ON DELETE SET NULL,
    actual_notes TEXT,  -- 実際のメモ（変更点など）
    status VARCHAR(50) DEFAULT 'completed',  -- completed, cancelled, modified
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- インデックス作成
-- ========================================
CREATE INDEX IF NOT EXISTS idx_route_selections_name ON route_selections(name);
CREATE INDEX IF NOT EXISTS idx_route_selections_created ON route_selections(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_route_results_name ON route_results(name);
CREATE INDEX IF NOT EXISTS idx_route_results_created ON route_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_route_history_date ON route_history(execution_date DESC);

-- ========================================
-- RLS (Row Level Security) 有効化
-- ========================================
ALTER TABLE route_selections ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_history ENABLE ROW LEVEL SECURITY;

-- 匿名ユーザー向けのポリシー（Supabase anon keyでのアクセス用）
-- 注意：本番運用では認証を追加することを推奨

CREATE POLICY "Allow all access to route_selections" ON route_selections
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all access to route_results" ON route_results
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all access to route_history" ON route_history
    FOR ALL USING (true) WITH CHECK (true);

-- ========================================
-- 使用方法
-- ========================================
-- 1. Supabase URLとanon keyをsecrets.tomlに設定
-- 2. このSQLをSupabaseのSQL Editorで実行
-- 3. アプリを再起動
