UPDATE business_settings SET value='VENTO'
WHERE key='business_name' AND value='VENITO';

UPDATE business_settings SET value='حلويات ومعجنات فينتو'
WHERE key='business_name_ar' AND value='حلويات ومعجنات فينيتو';

UPDATE product_categories
SET name_ar = CASE slug
    WHEN 'cakes' THEN 'الكيك والتورتات'
    WHEN 'pastries' THEN 'المعجنات والفطائر'
    WHEN 'arabic-sweets' THEN 'الحلويات الشرقية'
    WHEN 'western-desserts' THEN 'الحلويات الغربية'
    WHEN 'special-occasions' THEN 'بوكسات المناسبات'
END
WHERE (slug='cakes' AND name_ar='كيك')
   OR (slug='pastries' AND name_ar='معجنات')
   OR (slug='arabic-sweets' AND name_ar='حلويات شرقية')
   OR (slug='western-desserts' AND name_ar='حلويات غربية')
   OR (slug='special-occasions' AND name_ar='مناسبات خاصة');

INSERT OR IGNORE INTO product_categories
    (name_ar, slug, sort_order, active, created_at)
VALUES
    ('أطباق الضيافة', 'hospitality-trays', 8, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ('الشوكولاتة', 'chocolate', 9, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
