ALTER TABLE product_images ADD COLUMN image_data BLOB;
ALTER TABLE product_images ADD COLUMN image_mime_type TEXT;

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    receipt_number TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE,
    pdf_data BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_assets (
    asset_key TEXT PRIMARY KEY CHECK (asset_key IN ('logo')),
    content BLOB NOT NULL,
    mime_type TEXT NOT NULL CHECK (mime_type IN ('image/png', 'image/jpeg')),
    updated_at TEXT NOT NULL
);
