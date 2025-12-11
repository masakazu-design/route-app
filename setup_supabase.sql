-- ========================================
-- 環境整備スケジュール作成システム - Supabase テーブル作成SQL
-- ========================================
-- Supabaseの「SQL Editor」でこのスクリプトを実行してください

-- 旧テーブルを削除（既存データがある場合は注意）
DROP TABLE IF EXISTS route_history CASCADE;
DROP TABLE IF EXISTS route_results CASCADE;
DROP TABLE IF EXISTS route_selections CASCADE;

-- ========================================
-- スケジュール保存テーブル（統合版）
-- ========================================
CREATE TABLE IF NOT EXISTS route_schedules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,  -- 保存名（例：「12月第2週」）

    -- 選択状態
    selected_points JSONB,  -- 選択した訪問先名のリスト
    num_days INTEGER DEFAULT 2,  -- 日数設定

    -- 計算結果
    day_routes JSONB,  -- 日別ルート（インデックスリスト）
    selected_df JSONB,  -- 訪問先データ（DataFrame形式）
    timetables JSONB,  -- タイムテーブルデータ
    calendar_texts JSONB,  -- カレンダー用テキスト
    optimize_mode VARCHAR(20) DEFAULT 'distance',  -- 最適化モード

    -- メタデータ
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- 実行履歴テーブル
-- ========================================
CREATE TABLE IF NOT EXISTS route_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    schedule_id UUID REFERENCES route_schedules(id) ON DELETE SET NULL,
    execution_date DATE NOT NULL,  -- 実行日
    actual_notes TEXT,  -- メモ（変更点など）
    status VARCHAR(50) DEFAULT 'completed',  -- completed, cancelled, modified
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ========================================
-- インデックス作成
-- ========================================
CREATE INDEX IF NOT EXISTS idx_route_schedules_name ON route_schedules(name);
CREATE INDEX IF NOT EXISTS idx_route_schedules_created ON route_schedules(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_route_history_date ON route_history(execution_date DESC);

-- ========================================
-- RLS (Row Level Security) 有効化
-- ========================================
ALTER TABLE route_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE route_history ENABLE ROW LEVEL SECURITY;

-- 匿名ユーザー向けのポリシー
CREATE POLICY "Allow all access to route_schedules" ON route_schedules
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all access to route_history" ON route_history
    FOR ALL USING (true) WITH CHECK (true);

-- ========================================
-- 使用方法
-- ========================================
-- 1. Supabase URLとanon keyをsecrets.tomlに設定
-- 2. このSQLをSupabaseのSQL Editorで実行
-- 3. アプリを再起動
