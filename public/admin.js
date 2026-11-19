const adminState = { csrf: "", user: null, products: [], categories: [], areas: [], orders: [] };
const $$ = (selector) => document.querySelector(selector);
const formatMoney = (value) => value == null ? "يحدد لاحقاً" : `${Number(value).toLocaleString("ar-IQ")} د.ع`;
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const statusNames = {
  new: "طلب جديد", confirmed: "تم التأكيد", preparing: "قيد التحضير",
  ready: "جاهز للتوصيل", out_for_delivery: "خرج للتوصيل",
  delivered: "تم التوصيل", cancelled: "ملغي",
};
const dayNames = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"];
let searchTimers = {};
let toastTimer;

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET" && adminState.csrf) headers["X-CSRF-Token"] = adminState.csrf;
  const response = await fetch(path, {
    credentials: "same-origin", ...options, headers,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.includes("/login")) showLogin();
    throw new Error(data.error || "تعذر تنفيذ الطلب.");
  }
  return data;
}

function showToast(message) {
  const node = $$("#admin-toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("visible"), 3000);
}

function showLogin() {
  adminState.csrf = "";
  $$("#admin-app").classList.add("hidden");
  $$("#login-screen").classList.remove("hidden");
}

function showApp(user, csrf) {
  adminState.user = user;
  adminState.csrf = csrf;
  $$("#login-screen").classList.add("hidden");
  $$("#admin-app").classList.remove("hidden");
  $$("#sidebar-username").textContent = user.username;
  $$("#sidebar-role").textContent = ({ admin: "مدير النظام", manager: "مدير", staff: "موظف" })[user.role] || user.role;
  document.querySelectorAll(".admin-only").forEach((item) => item.classList.toggle("hidden", user.role !== "admin"));
  if (user.role === "staff") {
    document.querySelectorAll("[data-action]").forEach((item) => item.classList.add("hidden"));
  }
  $$("#today-date").textContent = new Intl.DateTimeFormat("ar-IQ", {
    weekday: "long", year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Baghdad",
  }).format(new Date());
  navigate("overview");
}

async function startSession() {
  try {
    const data = await request("/api/admin/session");
    showApp(data.user, data.csrfToken);
  } catch {
    showLogin();
  }
}

function statusPill(status) {
  return `<span class="status-pill status-${escapeHTML(status)}">${escapeHTML(statusNames[status] || status)}</span>`;
}

function emptyRow(columns, text = "لا توجد بيانات لعرضها حالياً.") {
  return `<tr><td class="empty-row" colspan="${columns}">${text}</td></tr>`;
}

function navigate(view) {
  const button = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (!button || button.classList.contains("hidden")) view = "overview";
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  document.querySelectorAll(".admin-view").forEach((item) => item.classList.toggle("active", item.dataset.panel === view));
  $$("#page-title").textContent = document.querySelector(`.nav-item[data-view="${view}"]`)?.textContent.trim() || "نظرة عامة";
  $$("#sidebar").classList.remove("open");
  loadView(view).catch((error) => showToast(error.message));
}

async function loadView(view) {
  if (view === "overview") return loadOverview();
  if (view === "products") return loadProducts();
  if (view === "categories") return loadCategories();
  if (view === "areas") return loadAreas();
  if (view === "orders") return loadOrders();
  if (view === "customers") return loadCustomers();
  if (view === "reports") return loadReports();
  if (view === "settings") return loadSettings();
  if (view === "banners") return loadBanners();
  if (view === "staff") return loadStaff();
}

function renderStats(container, items) {
  container.innerHTML = items.map((item) => `<article class="stat-card"><span>${escapeHTML(item.label)}</span><strong>${escapeHTML(item.value)}</strong><small>${escapeHTML(item.note || "")}</small></article>`).join("");
}

async function loadOverview() {
  const data = await request("/api/admin/summary");
  renderStats($$("#stats-grid"), [
    { label: "طلبات اليوم", value: Number(data.todayOrders).toLocaleString("ar-IQ"), note: "طلبات مسجلة اليوم" },
    { label: "مبيعات اليوم", value: formatMoney(data.todaySales), note: "لا تشمل الطلبات الملغاة" },
    { label: "المنتجات", value: Number(data.products).toLocaleString("ar-IQ"), note: "جميع المنتجات المسجلة" },
    { label: "طلبات جديدة", value: Number(data.statuses.new || 0).toLocaleString("ar-IQ"), note: "بانتظار المتابعة" },
  ]);
  $$("#recent-orders").innerHTML = data.recentOrders.length ? data.recentOrders.map((order) => `
    <tr><td><button class="inline-action" data-order="${escapeHTML(order.id || "")}" data-order-number="${escapeHTML(order.order_number)}">${escapeHTML(order.order_number)}</button></td>
    <td>${escapeHTML(order.full_name)}</td><td>${statusPill(order.status)}</td><td>${formatMoney(order.total_iqd)}</td>
    <td>${escapeHTML(new Date(order.created_at).toLocaleString("ar-IQ"))}</td></tr>`).join("") : emptyRow(5);
}

async function loadProducts() {
  const [products, categories] = await Promise.all([
    request("/api/admin/products"), request("/api/admin/categories"),
  ]);
  adminState.products = products;
  adminState.categories = categories;
  $$("#products-table").innerHTML = products.length ? products.map((product) => `
    <tr><td><strong>${escapeHTML(product.name_ar)}</strong>${product.featured ? " · مميز" : ""}</td>
    <td>${escapeHTML(product.category_name)}</td><td>${product.price_iqd == null ? "غير محدد" : formatMoney(product.price_iqd)}</td>
    <td>${product.available ? '<span class="status-pill status-ready">متاح</span>' : '<span class="status-pill status-cancelled">غير متاح</span>'}</td>
    <td><button class="inline-action" data-edit-product="${product.id}">تعديل</button><button class="inline-action" data-toggle-product="${product.id}">${product.available ? "إيقاف" : "تفعيل"}</button></td></tr>
  `).join("") : emptyRow(5, "لم تُضف منتجات بعد. أضيفوا منتجاتكم وأسعارها من هنا.");
}

async function loadCategories() {
  adminState.categories = await request("/api/admin/categories");
  $$("#categories-table").innerHTML = adminState.categories.length ? adminState.categories.map((category) => `
    <tr><td>${escapeHTML(category.name_ar)}</td><td dir="ltr">${escapeHTML(category.slug)}</td><td>${category.sort_order}</td>
    <td>${category.active ? "فعال" : "غير فعال"}</td><td><button class="inline-action" data-edit-category="${category.id}">تعديل</button></td></tr>
  `).join("") : emptyRow(5);
}

async function loadAreas() {
  adminState.areas = await request("/api/admin/areas");
  $$("#karkh-count").textContent = `${adminState.areas.filter((area) => area.district === "karkh").length} منطقة`;
  $$("#rusafa-count").textContent = `${adminState.areas.filter((area) => area.district === "rusafa").length} منطقة`;
  $$("#areas-table").innerHTML = adminState.areas.length ? adminState.areas.map((area) => `
    <tr><td>${escapeHTML(area.name_ar)}</td><td>${area.district === "karkh" ? "الكرخ" : "الرصافة"}</td>
    <td>${area.fee_iqd == null ? '<span class="status-pill status-cancelled">يحدد لاحقاً</span>' : formatMoney(area.fee_iqd)}</td>
    <td>${area.active ? '<span class="status-pill status-ready">فعالة</span>' : '<span class="status-pill">غير فعالة</span>'}</td>
    <td><button class="inline-action" data-edit-area="${area.id}">تعديل</button><button class="inline-action" data-toggle-area="${area.id}">${area.active ? "إيقاف" : "تفعيل"}</button></td></tr>
  `).join("") : emptyRow(5, "لم تُضف مناطق توصيل بعد. لا يمكن تأكيد الطلبات قبل ضبط المناطق ورسومها.");
}

async function loadOrders() {
  const params = new URLSearchParams();
  if ($$("#order-search").value.trim()) params.set("q", $$("#order-search").value.trim());
  if ($$("#order-status").value) params.set("status", $$("#order-status").value);
  adminState.orders = await request(`/api/admin/orders?${params}`);
  $$("#orders-table").innerHTML = adminState.orders.length ? adminState.orders.map((order) => `
    <tr><td><button class="inline-action" data-order="${order.id}">${escapeHTML(order.order_number)}</button></td>
    <td>${escapeHTML(order.full_name)}<br><small>${escapeHTML(order.phone)}</small></td>
    <td>${escapeHTML(order.delivery_area_name)}</td><td>${statusPill(order.status)}</td>
    <td>${formatMoney(order.total_iqd)}</td><td>${escapeHTML(new Date(order.created_at).toLocaleString("ar-IQ"))}</td>
    <td><button class="inline-action" data-order="${order.id}">التفاصيل</button></td></tr>
  `).join("") : emptyRow(7, "لا توجد طلبات تطابق البحث.");
}

async function openOrder(orderId) {
  const order = await request(`/api/admin/orders/${orderId}`);
  const dialog = $$("#admin-dialog");
  $$("#dialog-content").innerHTML = `
    <div class="modal-form">
      <span class="eyebrow eyebrow-dark">تفاصيل الطلب</span><h2>${escapeHTML(order.order_number)}</h2>
      <div class="order-detail-grid">
        <div><span>العميل</span><strong>${escapeHTML(order.full_name)}</strong></div>
        <div><span>رقم الهاتف</span><a href="tel:${escapeHTML(order.phone)}">${escapeHTML(order.phone)}</a></div>
        <div><span>منطقة التوصيل</span><strong>${escapeHTML(order.delivery_area_name)} — ${order.delivery_district === "karkh" ? "الكرخ" : "الرصافة"}</strong></div>
        <div><span>أجرة التوصيل</span><strong>${formatMoney(order.delivery_fee_iqd)}</strong></div>
        <div><span>العنوان</span><strong>${escapeHTML(order.delivery_address)}</strong></div>
        <div><span>الدفع</span><strong>${order.payment_method === "cash_on_delivery" ? "نقداً عند الاستلام" : "إلكتروني"} · ${order.payment_status === "pending" ? "بانتظار الدفع" : escapeHTML(order.payment_status)}</strong></div>
        ${order.delivery_instructions ? `<div><span>ملاحظات</span><strong>${escapeHTML(order.delivery_instructions)}</strong></div>` : ""}
      </div>
      <div>${order.items.map((item) => `<div class="order-item"><span>${escapeHTML(item.product_name_ar)} ${item.variant_name_ar ? `— ${escapeHTML(item.variant_name_ar)}` : ""} × ${item.quantity}</span><strong>${formatMoney(item.line_total_iqd)}</strong></div>`).join("")}</div>
      <div class="order-detail-grid"><div><span>المجموع الفرعي</span><strong>${formatMoney(order.subtotal_iqd)}</strong></div><div><span>الإجمالي</span><strong>${formatMoney(order.total_iqd)}</strong></div></div>
      <div class="order-detail-actions">
        <label>تحديث حالة الطلب<select id="order-status-update">${Object.entries(statusNames).map(([key, value]) => `<option value="${key}" ${order.status === key ? "selected" : ""}>${escapeHTML(value)}</option>`).join("")}</select></label>
        <button class="button button-primary mini-button" data-save-order="${order.id}">حفظ الحالة</button>
        <button class="button button-secondary mini-button" data-print-order="${order.id}" data-print-target="receipt">طباعة الإيصال</button>
        <button class="button button-secondary mini-button" data-print-order="${order.id}" data-print-target="kitchen">تذكرة المطبخ</button>
      </div>
      <p class="notification-note">سجل الحالة: ${order.history.map((entry) => `${escapeHTML(statusNames[entry.status] || entry.status)} (${escapeHTML(new Date(entry.created_at).toLocaleString("ar-IQ"))})`).join(" ← ")}</p>
    </div>`;
  dialog.showModal();
}

async function loadCustomers() {
  const params = new URLSearchParams();
  if ($$("#customer-search").value.trim()) params.set("q", $$("#customer-search").value.trim());
  const customers = await request(`/api/admin/customers?${params}`);
  $$("#customers-table").innerHTML = customers.length ? customers.map((customer) => `
    <tr><td>${escapeHTML(customer.full_name)}</td><td><a href="tel:${escapeHTML(customer.phone)}" dir="ltr">${escapeHTML(customer.phone)}</a></td>
    <td>${customer.order_count}</td><td>${formatMoney(customer.total_spent)}</td>
    <td>${escapeHTML(new Date(customer.created_at).toLocaleDateString("ar-IQ"))}</td></tr>
  `).join("") : emptyRow(5, "لا توجد سجلات عملاء.");
}

async function loadReports() {
  const data = await request(`/api/admin/reports?period=${encodeURIComponent($$("#report-period").value)}`);
  renderStats($$("#report-stats"), [
    { label: "عدد الطلبات", value: Number(data.summary.orders || 0).toLocaleString("ar-IQ"), note: "ضمن الفترة المحددة" },
    { label: "إجمالي المبيعات", value: formatMoney(data.summary.sales), note: "باستثناء الطلبات الملغاة" },
    { label: "رسوم التوصيل", value: formatMoney(data.summary.delivery_fees), note: "من الطلبات غير الملغاة" },
    { label: "طلبات ملغاة", value: Number(data.summary.cancelled || 0).toLocaleString("ar-IQ"), note: "ضمن الفترة المحددة" },
  ]);
  $$("#daily-report").innerHTML = data.daily.length ? data.daily.map((row) =>
    `<tr><td>${escapeHTML(row.day)}</td><td>${row.orders}</td><td>${formatMoney(row.sales)}</td></tr>`
  ).join("") : emptyRow(3);
  $$("#best-sellers").innerHTML = data.bestSellers.length ? data.bestSellers.map((row) =>
    `<tr><td>${escapeHTML(row.product_name_ar)}</td><td>${row.quantity}</td><td>${formatMoney(row.sales)}</td></tr>`
  ).join("") : emptyRow(3);
  $$("#payments-report").innerHTML = data.payments.length ? data.payments.map((row) =>
    `<tr><td>${row.payment_method === "cash_on_delivery" ? "نقداً عند الاستلام" : "إلكتروني"}</td><td>${row.orders}</td><td>${formatMoney(row.paid)}</td></tr>`
  ).join("") : emptyRow(3);
}

async function loadSettings() {
  const data = await request("/api/admin/settings");
  const form = $$("#settings-form");
  for (const [key, value] of Object.entries(data.settings)) {
    const field = form.elements.namedItem(key);
    if (!field) continue;
    if (field.type === "checkbox") field.checked = value === "1";
    else field.value = value;
  }
  $$("#hours-table").innerHTML = data.hours.map((hour) => `
    <tr><td>${dayNames[hour.weekday]}</td><td><input type="time" data-hour="opensAt" data-day="${hour.weekday}" value="${escapeHTML(hour.opens_at)}"></td>
    <td><input type="time" data-hour="closesAt" data-day="${hour.weekday}" value="${escapeHTML(hour.closes_at)}"></td>
    <td><input type="checkbox" data-hour="active" data-day="${hour.weekday}" ${hour.active ? "checked" : ""} aria-label="تفعيل ${dayNames[hour.weekday]}"></td></tr>
  `).join("");
}

async function loadBanners() {
  const banners = await request("/api/admin/banners");
  $$("#banners-table").innerHTML = banners.length ? banners.map((banner) => `
    <tr><td>${escapeHTML(banner.title_ar)}</td><td>${escapeHTML(banner.description_ar)}</td>
    <td>${banner.image_url ? "صورة مضافة" : "بدون صورة"}</td><td>${banner.active ? "فعال" : "غير فعال"}</td>
    <td><button class="inline-action" data-edit-banner="${banner.id}">تعديل</button><button class="inline-action" data-delete-banner="${banner.id}">حذف</button></td></tr>
  `).join("") : emptyRow(5, "لا توجد عروض ترويجية.");
}

async function loadStaff() {
  const users = await request("/api/admin/staff");
  $$("#staff-table").innerHTML = users.length ? users.map((user) => `
    <tr><td>${escapeHTML(user.username)}</td><td>${({ admin: "مدير النظام", manager: "مدير", staff: "موظف" })[user.role]}</td>
    <td>${user.active ? "فعال" : "موقوف"}</td><td>${escapeHTML(new Date(user.created_at).toLocaleDateString("ar-IQ"))}</td></tr>
  `).join("") : emptyRow(4);
}

function openDialog(content) {
  $$("#dialog-content").innerHTML = content;
  $$("#admin-dialog").showModal();
}

function checkbox(name, label, checked) {
  return `<label class="checkbox-label"><input name="${name}" type="checkbox" ${checked ? "checked" : ""}>${label}</label>`;
}

function productForm(product = null) {
  const categories = adminState.categories.length ? adminState.categories : [];
  const variants = (product?.variants || []).map((item) => `${item.name_ar}|${item.price_iqd ?? ""}`).join("\n");
  openDialog(`<form class="modal-form" id="product-form" data-id="${product?.id || ""}">
    <span class="eyebrow eyebrow-dark">${product ? "تعديل بيانات المنتج" : "إضافة منتج جديد"}</span><h2>${product ? escapeHTML(product.name_ar) : "منتج جديد"}</h2>
    <label>اسم المنتج بالعربية<input name="name" required maxlength="160" value="${escapeHTML(product?.name_ar || "")}"></label>
    <label>التصنيف<select name="categoryId" required>${categories.map((category) => `<option value="${category.id}" ${product?.category_id === category.id ? "selected" : ""}>${escapeHTML(category.name_ar)}</option>`).join("")}</select></label>
    <label>السعر الأساسي بالدينار العراقي<input name="price" type="number" min="1" value="${product?.price_iqd ?? ""}" placeholder="اتركوه فارغاً حتى تحديد السعر"></label>
    <label>الوصف<textarea name="description" maxlength="2000">${escapeHTML(product?.description_ar || "")}</textarea></label>
    <label>رابط الصورة (https:// أو مسار محلي)<input name="image" dir="ltr" value="${escapeHTML(product?.images?.[0] || "")}" placeholder="https://..."></label>
    <label>الأحجام والخيارات (خيار لكل سطر: الاسم|السعر)<textarea name="variants" placeholder="صغير|&#10;كبير|">${escapeHTML(variants)}</textarea></label>
    ${checkbox("available", "متاح للطلب", product ? !!product.available : true)}
    ${checkbox("featured", "منتج مميز", !!product?.featured)}
    ${checkbox("isNew", "منتج جديد", !!product?.is_new)}
    <div class="modal-actions"><button class="button button-primary" type="submit">حفظ المنتج</button><button class="button button-secondary" type="button" data-close-dialog>إلغاء</button></div>
  </form>`);
}

function categoryForm(category = null) {
  openDialog(`<form class="modal-form" id="category-form" data-id="${category?.id || ""}">
    <span class="eyebrow eyebrow-dark">${category ? "تعديل التصنيف" : "تصنيف جديد"}</span><h2>${category ? escapeHTML(category.name_ar) : "إضافة تصنيف"}</h2>
    <label>اسم التصنيف بالعربية<input name="name" required maxlength="100" value="${escapeHTML(category?.name_ar || "")}"></label>
    <label>المعرّف الإنجليزي<input name="slug" required maxlength="100" pattern="[a-z0-9-]+" dir="ltr" placeholder="western-desserts" value="${escapeHTML(category?.slug || `category-${Date.now()}`)}"></label>
    <label>ترتيب العرض<input name="sortOrder" type="number" min="0" value="${category?.sort_order ?? 0}"></label>
    ${checkbox("active", "تصنيف فعال", category ? !!category.active : true)}
    <div class="modal-actions"><button class="button button-primary" type="submit">حفظ</button><button class="button button-secondary" type="button" data-close-dialog>إلغاء</button></div>
  </form>`);
}

function areaForm(area = null) {
  openDialog(`<form class="modal-form" id="area-form" data-id="${area?.id || ""}">
    <span class="eyebrow eyebrow-dark">${area ? "تعديل المنطقة" : "منطقة توصيل جديدة"}</span><h2>${area ? escapeHTML(area.name_ar) : "إضافة منطقة"}</h2>
    <label>اسم المنطقة<input name="name" required maxlength="120" value="${escapeHTML(area?.name_ar || "")}"></label>
    <label>جانب بغداد<select name="district" required><option value="karkh" ${area?.district === "karkh" ? "selected" : ""}>الكرخ</option><option value="rusafa" ${area?.district === "rusafa" ? "selected" : ""}>الرصافة</option></select></label>
    <label>أجرة التوصيل بالدينار العراقي<input name="fee" type="number" min="0" value="${area?.fee_iqd ?? ""}" placeholder="اتركوه فارغاً لحين تحديد الأجرة"></label>
    ${checkbox("active", "منطقة فعالة", area ? !!area.active : true)}
    <div class="modal-actions"><button class="button button-primary" type="submit">حفظ المنطقة</button><button class="button button-secondary" type="button" data-close-dialog>إلغاء</button></div>
  </form>`);
}

function bannerForm(banner = null) {
  openDialog(`<form class="modal-form" id="banner-form" data-id="${banner?.id || ""}">
    <span class="eyebrow eyebrow-dark">محتوى واجهة المتجر</span><h2>${banner ? "تعديل البانر" : "إضافة بانر"}</h2>
    <label>العنوان بالعربية<input name="title" required maxlength="160" value="${escapeHTML(banner?.title_ar || "")}"></label>
    <label>الوصف<textarea name="description" maxlength="1000">${escapeHTML(banner?.description_ar || "")}</textarea></label>
    <label>رابط الصورة (اختياري)<input name="imageUrl" dir="ltr" value="${escapeHTML(banner?.image_url || "")}"></label>
    <label>ترتيب العرض<input name="sortOrder" type="number" min="0" value="${banner?.sort_order ?? 0}"></label>
    ${checkbox("active", "بانر فعال", banner ? !!banner.active : true)}
    <div class="modal-actions"><button class="button button-primary" type="submit">حفظ</button><button class="button button-secondary" type="button" data-close-dialog>إلغاء</button></div>
  </form>`);
}

function staffForm() {
  openDialog(`<form class="modal-form" id="staff-form">
    <span class="eyebrow eyebrow-dark">صلاحيات الفريق</span><h2>إضافة مستخدم</h2>
    <label>اسم المستخدم (إنجليزي)<input name="username" required minlength="3" maxlength="80" pattern="[A-Za-z0-9_.-]+" dir="ltr"></label>
    <label>كلمة المرور (12 حرفاً على الأقل)<input name="password" type="password" required minlength="12" autocomplete="new-password"></label>
    <label>الدور<select name="role"><option value="staff">موظف — عرض البيانات فقط</option><option value="manager">مدير — إدارة الطلبات والبيانات</option><option value="admin">مدير النظام — جميع الصلاحيات</option></select></label>
    <div class="modal-actions"><button class="button button-primary" type="submit">إنشاء الحساب</button><button class="button button-secondary" type="button" data-close-dialog>إلغاء</button></div>
  </form>`);
}

async function saveProduct(form) {
  const values = new FormData(form);
  const image = values.get("image").trim();
  const variants = values.get("variants").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name, price = ""] = line.split("|");
    return { name: name.trim(), price: price.trim() };
  });
  const payload = {
    name: values.get("name").trim(), categoryId: Number(values.get("categoryId")),
    price: values.get("price") || null, description: values.get("description"),
    images: image ? [image] : [], variants,
    available: values.has("available"), featured: values.has("featured"),
    isNew: values.has("isNew"), sortOrder: 0,
  };
  const id = form.dataset.id;
  await request(`/api/admin/products${id ? `/${id}` : ""}`, {
    method: id ? "PUT" : "POST", body: JSON.stringify(payload),
  });
  $$("#admin-dialog").close();
  await loadProducts();
  showToast("تم حفظ بيانات المنتج.");
}

async function submitSettings(form) {
  const settings = {};
  for (const [key, value] of new FormData(form).entries()) settings[key] = value;
  for (const key of ["payment_cash_enabled", "payment_electronic_enabled", "printer_enabled"]) {
    settings[key] = form.elements.namedItem(key).checked;
  }
  const hours = dayNames.map((_, weekday) => ({
    weekday,
    opensAt: form.querySelector(`[data-hour="opensAt"][data-day="${weekday}"]`).value,
    closesAt: form.querySelector(`[data-hour="closesAt"][data-day="${weekday}"]`).value,
    active: form.querySelector(`[data-hour="active"][data-day="${weekday}"]`).checked,
  }));
  await request("/api/admin/settings", { method: "PUT", body: JSON.stringify({ settings, hours }) });
  showToast("حُفظت إعدادات المتجر.");
  await loadSettings();
}

async function handleSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  try {
    if (form.id === "product-form") return await saveProduct(form);
    if (form.id === "category-form") {
      const values = new FormData(form);
      const payload = { name: values.get("name").trim(), slug: values.get("slug").trim(),
        sortOrder: Number(values.get("sortOrder") || 0), active: values.has("active") };
      const id = form.dataset.id;
      await request(`/api/admin/categories${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
      $$("#admin-dialog").close();
      await loadCategories();
      showToast("تم حفظ التصنيف.");
    } else if (form.id === "area-form") {
      const values = new FormData(form);
      const payload = { name: values.get("name").trim(), district: values.get("district"),
        fee: values.get("fee") || null, active: values.has("active") };
      const id = form.dataset.id;
      await request(`/api/admin/areas${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
      $$("#admin-dialog").close();
      await loadAreas();
      showToast("تم حفظ منطقة التوصيل.");
    } else if (form.id === "banner-form") {
      const values = new FormData(form);
      const payload = { title: values.get("title").trim(), description: values.get("description"),
        imageUrl: values.get("imageUrl").trim(), sortOrder: Number(values.get("sortOrder") || 0), active: values.has("active") };
      const id = form.dataset.id;
      await request(`/api/admin/banners${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
      $$("#admin-dialog").close();
      await loadBanners();
      showToast("تم حفظ البانر.");
    } else if (form.id === "staff-form") {
      const values = new FormData(form);
      await request("/api/admin/staff", { method: "POST", body: JSON.stringify(Object.fromEntries(values.entries())) });
      $$("#admin-dialog").close();
      await loadStaff();
      showToast("أُنشئ حساب المستخدم.");
    } else if (form.id === "settings-form") {
      $$("#settings-error").classList.add("hidden");
      try {
        await submitSettings(form);
      } catch (error) {
        $$("#settings-error").textContent = error.message;
        $$("#settings-error").classList.remove("hidden");
      }
    } else if (form.id === "login-form") {
      $$("#login-error").classList.add("hidden");
      const submit = form.querySelector("button[type=submit]");
      submit.disabled = true;
      try {
        const values = new FormData(form);
        const data = await request("/api/admin/login", { method: "POST", body: JSON.stringify(Object.fromEntries(values.entries())) });
        form.reset();
        showApp(data.user, data.csrfToken);
      } catch (error) {
        $$("#login-error").textContent = error.message;
        $$("#login-error").classList.remove("hidden");
      } finally {
        submit.disabled = false;
      }
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function eventClick(event) {
  const nav = event.target.closest("[data-view]");
  if (nav) return navigate(nav.dataset.view);
  const jump = event.target.closest("[data-jump]");
  if (jump) return navigate(jump.dataset.jump);
  if (event.target.closest("[data-close-dialog]")) return $$("#admin-dialog").close();
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "add-product") {
    if (!adminState.categories.length) await loadCategories();
    return productForm();
  }
  if (action === "add-category") return categoryForm();
  if (action === "add-area") return areaForm();
  if (action === "add-banner") return bannerForm();
  if (action === "add-staff") return staffForm();

  const editProduct = event.target.closest("[data-edit-product]");
  if (editProduct) {
    const product = adminState.products.find((item) => item.id === Number(editProduct.dataset.editProduct));
    if (product) productForm(product);
    return;
  }
  const editCategory = event.target.closest("[data-edit-category]");
  if (editCategory) {
    const category = adminState.categories.find((item) => item.id === Number(editCategory.dataset.editCategory));
    if (category) categoryForm(category);
    return;
  }
  const editArea = event.target.closest("[data-edit-area]");
  if (editArea) {
    const area = adminState.areas.find((item) => item.id === Number(editArea.dataset.editArea));
    if (area) areaForm(area);
    return;
  }
  const editBanner = event.target.closest("[data-edit-banner]");
  if (editBanner) {
    const banners = await request("/api/admin/banners");
    const banner = banners.find((item) => item.id === Number(editBanner.dataset.editBanner));
    if (banner) bannerForm(banner);
    return;
  }
  const toggleProduct = event.target.closest("[data-toggle-product]");
  if (toggleProduct) {
    const product = adminState.products.find((item) => item.id === Number(toggleProduct.dataset.toggleProduct));
    if (product) {
      await request(`/api/admin/products/${product.id}`, { method: "PUT", body: JSON.stringify({
        name: product.name_ar, categoryId: product.category_id, price: product.price_iqd,
        description: product.description_ar, images: product.images,
        variants: product.variants.map((item) => ({ name: item.name_ar, price: item.price_iqd, available: !!item.available })),
        available: !product.available, featured: !!product.featured, isNew: !!product.is_new,
        sortOrder: product.sort_order,
      }) });
      await loadProducts();
      showToast("تم تحديث توفر المنتج.");
    }
    return;
  }
  const toggleArea = event.target.closest("[data-toggle-area]");
  if (toggleArea) {
    const area = adminState.areas.find((item) => item.id === Number(toggleArea.dataset.toggleArea));
    if (area) {
      await request(`/api/admin/areas/${area.id}`, { method: "PUT", body: JSON.stringify({
        name: area.name_ar, district: area.district, fee: area.fee_iqd, active: !area.active,
      }) });
      await loadAreas();
      showToast("تم تحديث حالة المنطقة.");
    }
    return;
  }
  const deleteBanner = event.target.closest("[data-delete-banner]");
  if (deleteBanner && window.confirm("هل تريدون حذف هذا البانر؟")) {
    await request(`/api/admin/banners/${deleteBanner.dataset.deleteBanner}`, { method: "DELETE" });
    await loadBanners();
    showToast("حُذف البانر.");
    return;
  }
  const order = event.target.closest("[data-order]");
  if (order) {
    const id = order.dataset.order;
    if (!id) {
      const found = adminState.orders.find((item) => item.order_number === order.dataset.orderNumber);
      if (found) return openOrder(found.id);
      return;
    }
    return openOrder(id);
  }
  const saveOrder = event.target.closest("[data-save-order]");
  if (saveOrder) {
    await request(`/api/admin/orders/${saveOrder.dataset.saveOrder}`, {
      method: "PUT", body: JSON.stringify({ status: $$("#order-status-update").value }),
    });
    $$("#admin-dialog").close();
    await loadOrders();
    showToast("تم تحديث حالة الطلب.");
    return;
  }
  const printOrder = event.target.closest("[data-print-order]");
  if (printOrder) {
    printOrder.disabled = true;
    try {
      const result = await request(`/api/admin/orders/${printOrder.dataset.printOrder}/print`, {
        method: "POST", body: JSON.stringify({ target: printOrder.dataset.printTarget }),
      });
      showToast(result.message);
    } finally {
      printOrder.disabled = false;
    }
    return;
  }
  const printerTest = event.target.closest("#printer-test-button");
  if (printerTest) {
    printerTest.disabled = true;
    try {
      const result = await request("/api/admin/printer-test", { method: "POST", body: "{}" });
      showToast(result.message);
    } finally {
      printerTest.disabled = false;
    }
    return;
  }
  if (event.target.closest("#logout-button")) {
    try {
      await request("/api/admin/logout", { method: "POST", body: "{}" });
    } finally {
      showLogin();
    }
  }
}

function debounceLoad(field, view, delay = 250) {
  field.addEventListener("input", () => {
    clearTimeout(searchTimers[field.id]);
    searchTimers[field.id] = setTimeout(() => loadView(view).catch((error) => showToast(error.message)), delay);
  });
}

document.addEventListener("submit", (event) => handleSubmit(event));
document.addEventListener("click", (event) => {
  eventClick(event).catch((error) => showToast(error.message));
});
$$("admin-menu-toggle").addEventListener("click", () => $$("#sidebar").classList.toggle("open"));
$$("order-status").addEventListener("change", () => loadOrders().catch((error) => showToast(error.message)));
$$("report-period").addEventListener("change", () => loadReports().catch((error) => showToast(error.message)));
debounceLoad($$("#order-search"), "orders");
debounceLoad($$("#customer-search"), "customers");
startSession();
