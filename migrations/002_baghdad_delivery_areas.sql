ALTER TABLE orders ADD COLUMN delivery_fee_determined INTEGER NOT NULL DEFAULT 1
    CHECK (delivery_fee_determined IN (0, 1));

INSERT INTO delivery_areas (name_ar,district,fee_iqd,active,created_at)
SELECT seed.name_ar,seed.district,seed.fee_iqd,1,strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM (
    SELECT 'مدينة الصدر' AS name_ar,'rusafa' AS district,2000 AS fee_iqd UNION ALL
    SELECT 'البنوك','rusafa',1000 UNION ALL
    SELECT 'الشعب','rusafa',1000 UNION ALL
    SELECT 'حي أور','rusafa',NULL UNION ALL
    SELECT 'شارع فلسطين','rusafa',NULL UNION ALL
    SELECT 'باب المعظم','rusafa',3000 UNION ALL
    SELECT 'الأعظمية','rusafa',NULL UNION ALL
    SELECT 'الكرادة','rusafa',NULL UNION ALL
    SELECT 'الكرادة داخل','rusafa',NULL UNION ALL
    SELECT 'الكرادة خارج','rusafa',NULL UNION ALL
    SELECT 'زيونة','rusafa',NULL UNION ALL
    SELECT 'بغداد الجديدة','rusafa',NULL UNION ALL
    SELECT 'البلديات','rusafa',NULL UNION ALL
    SELECT 'الغدير','rusafa',NULL UNION ALL
    SELECT 'المشتل','rusafa',NULL UNION ALL
    SELECT 'الأمين','rusafa',NULL UNION ALL
    SELECT 'الفضيلية','rusafa',NULL UNION ALL
    SELECT 'جميلة','rusafa',NULL UNION ALL
    SELECT 'العبيدي','rusafa',NULL UNION ALL
    SELECT 'الحسينية','rusafa',NULL UNION ALL
    SELECT 'سبع قصور','rusafa',NULL UNION ALL
    SELECT 'الطالبية','rusafa',NULL UNION ALL
    SELECT 'القاهرة','rusafa',NULL UNION ALL
    SELECT 'الوزيرية','rusafa',NULL UNION ALL
    SELECT 'باب الشرقي','rusafa',NULL UNION ALL
    SELECT 'شارع السعدون','rusafa',NULL UNION ALL
    SELECT 'شارع النضال','rusafa',NULL UNION ALL
    SELECT 'كمب سارة','rusafa',NULL UNION ALL
    SELECT 'حي الوحدة','rusafa',NULL UNION ALL
    SELECT 'الزعفرانية','rusafa',NULL UNION ALL
    SELECT 'النهروان','rusafa',NULL UNION ALL
    SELECT 'المنصور','karkh',NULL UNION ALL
    SELECT 'الحرية','karkh',NULL UNION ALL
    SELECT 'الشرطة الرابعة','karkh',NULL UNION ALL
    SELECT 'الشرطة الثانية','karkh',NULL UNION ALL
    SELECT 'الشعلة','karkh',NULL UNION ALL
    SELECT 'الغزالية','karkh',NULL UNION ALL
    SELECT 'حي الجامعة','karkh',NULL UNION ALL
    SELECT 'العامرية','karkh',NULL UNION ALL
    SELECT 'الخضراء','karkh',NULL UNION ALL
    SELECT 'العدل','karkh',NULL UNION ALL
    SELECT 'القادسية','karkh',NULL UNION ALL
    SELECT 'اليرموك','karkh',NULL UNION ALL
    SELECT 'الحارثية','karkh',NULL UNION ALL
    SELECT 'الداودي','karkh',NULL UNION ALL
    SELECT 'الوشاش','karkh',NULL UNION ALL
    SELECT 'العطيفية','karkh',NULL UNION ALL
    SELECT 'الكاظمية','karkh',NULL UNION ALL
    SELECT 'الكريعات','karkh',NULL UNION ALL
    SELECT 'أبو غريب','karkh',NULL UNION ALL
    SELECT 'السيدية','karkh',NULL UNION ALL
    SELECT 'البياع','karkh',NULL UNION ALL
    SELECT 'الدورة','karkh',NULL UNION ALL
    SELECT 'حي العامل','karkh',NULL UNION ALL
    SELECT 'الجهاد','karkh',NULL UNION ALL
    SELECT 'الشرطة الخامسة','karkh',NULL UNION ALL
    SELECT 'حي الفرات','karkh',NULL UNION ALL
    SELECT 'حي الرسالة','karkh',NULL UNION ALL
    SELECT 'الإعلام','karkh',NULL UNION ALL
    SELECT 'المأمون','karkh',NULL
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM delivery_areas current
    WHERE current.name_ar=seed.name_ar AND current.district=seed.district
);

UPDATE delivery_areas SET fee_iqd=2000
WHERE name_ar='مدينة الصدر' AND district='rusafa';
UPDATE delivery_areas SET fee_iqd=1000
WHERE name_ar IN ('البنوك','الشعب') AND district='rusafa';
UPDATE delivery_areas SET fee_iqd=3000
WHERE name_ar='باب المعظم' AND district='rusafa';