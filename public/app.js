const state = {
  categories: [],
  products: [],
  cart: [],
  areas: [],
  category: "",
  search: "",
  collectionGroup: "featured",
  collections: {},
  storeOpen: false,
  storeStatusAvailable: false,
  cashPaymentEnabled: true,
  selectedAreaId: localStorage.getItem("venito_delivery_area") || "",
};

const $ = (selector) => document.querySelector(selector);
const money = (amount) => amount == null
  ? "السعر يحدد لاحقاً"
  : `${Number(amount).toLocaleString("ar-IQ")} د.ع`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
let toastTimer;
let notificationTimer;
let currentReceiptUrl = "";

function showNotification(message) {
  const island = $("#notification-island");
  $("#notification-island-copy").textContent = message;
  island.classList.add("visible");
  island.setAttribute("aria-hidden", "false");
  clearTimeout(notificationTimer);
  notificationTimer = setTimeout(() => {
    island.classList.remove("visible");
    island.setAttribute("aria-hidden", "true");
  }, 3800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "تعذر إكمال الطلب. حاولوا مرة أخرى.");
  return payload;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("visible"), 2800);
}

const categoryPhotos = {
  all: "photo-1606313564200-e75d5e30476c",
  cakes: "photo-1578985545062-69928b1d9587",
  pastries: "photo-1555507036-ab1f4038808a",
  croissants: "photo-1555507036-ab1f4038808a",
  cookies: "photo-1499636136210-6f4ee915583e",
  "arabic-sweets": "photo-1606312619070-d48b4c652a52",
  "western-desserts": "photo-1606313564200-e75d5e30476c",
  "special-occasions": "photo-1578985545062-69928b1d9587",
  "hospitality-trays": "photo-1555507036-ab1f4038808a",
  chocolate: "photo-1606313564200-e75d5e30476c",
};

function categoryPhoto(slug = "all", imageUrl = "") {
  if (imageUrl) return imageUrl;
  const image = categoryPhotos[slug] || categoryPhotos.all;
  return `https://images.unsplash.com/${image}?auto=format&fit=crop&w=700&q=85`;
}

function renderCategories() {
  const all = `<button class="category-chip category-card all-category ${state.category === "" ? "active" : ""}" data-category="">
    <span class="category-icon" aria-hidden="true" style="--category-photo:url('${categoryPhoto()}')"><span class="category-grid-icon">▦</span></span>
    <span class="category-number">01</span><span class="category-name">كل المنتجات</span></button>`;
  $("#categories").innerHTML = all + state.categories.map((category) =>
    `<button class="category-chip category-card ${state.category === String(category.id) ? "active" : ""}" data-category="${category.id}">
      <span class="category-icon" aria-hidden="true" style="--category-photo:url('${categoryPhoto(category.slug, category.image_url)}')"></span>
      <span class="category-number">${String(state.categories.indexOf(category) + 2).padStart(2, "0")}</span>
      <span class="category-name">${esc(category.name_ar)}</span></button>`
  ).join("");
}

function categoryIcon(slug = "", name = "") {
  const label = `${slug} ${name}`.toLowerCase();
  let drawing = '<path d="M4 10h16l-1 10H5L4 10Z"/><path d="M3 10 5 4h14l2 6M8 10V7m4 3V7m4 3V7"/>';
  if (/cake|كيك|تورت/.test(label)) drawing = '<path d="M4 12h16v8H4zM4 12c0-2 2-3 4-2 2-3 6-3 8 0 2-1 4 0 4 2M8 8V5m8 3V5"/>';
  else if (/arabic|شرقي|بقلاو|كن/.test(label)) drawing = '<path d="m12 3 8 5-8 5-8-5 8-5Zm-8 9 8 5 8-5M4 16l8 5 8-5"/>';
  else if (/western|غربي|كوكي|شوكولاتة/.test(label)) drawing = '<path d="M12 3a9 9 0 1 0 9 9 3 3 0 0 1-4-4 3 3 0 0 1-5-5Z"/><circle cx="8" cy="12" r="1"/><circle cx="12" cy="16" r="1"/>';
  else if (/pastr|croissant|معجن|كرواس|فطير/.test(label)) drawing = '<path d="M4 17c0-7 4-12 8-12s8 5 8 12H4Z"/><path d="M7 17c0-5 2-8 5-8s5 3 5 8m-7-8-2-3m7 3 2-3"/>';
  else if (/gift|occasion|مناسب|بوكس|ضيافة/.test(label)) drawing = '<path d="M4 10h16v11H4zM3 7h18v3H3zM12 7c-5 0-5-5-2-5 2 0 2 3 2 5Zm0 0c0-5 4-6 5-4s-1 4-5 4Zm0 0v14"/>';
  else if (/drink|مشروب/.test(label)) drawing = '<path d="M6 4h12l-1 17H7L6 4Zm2-1h8M9 8h6"/>';
  else if (/all|الكل/.test(label)) drawing = '<rect x="4" y="4" width="6" height="6" rx="2"/><rect x="14" y="4" width="6" height="6" rx="2"/><rect x="4" y="14" width="6" height="6" rx="2"/><rect x="14" y="14" width="6" height="6" rx="2"/>';
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${drawing}</svg>`;
}

function productCard(product) {
  const image = product.images?.[0];
  const variants = product.variants || [];
  const initialPrice = variants.length ? null : product.price_iqd;
  return `<article class="product-card" data-product-card="${product.id}">
      <div class="product-image">${image
        ? `<img src="${esc(image)}" alt="${esc(product.name_ar)}" loading="lazy"><div class="product-placeholder" hidden>✳</div>`
        : `<div class="product-placeholder" aria-hidden="true">✳</div>`}
        <span class="product-availability">متوفر</span>
        ${product.is_new ? '<span class="product-badge">جديد</span>' : product.featured ? '<span class="product-badge">مختار لك</span>' : ""}
        <button class="favorite-button" type="button" data-favorite="${product.id}" aria-label="إضافة ${esc(product.name_ar)} للمفضلة">♡</button>
        <button class="product-details-trigger" type="button" data-details="${product.id}" aria-label="تفاصيل المنتج"></button>
      </div>
      <div class="product-info">
        <h3><button class="product-title-trigger" type="button" data-details="${product.id}">${esc(product.name_ar)}</button></h3>
        <p class="product-description">${esc(product.description_ar || "نحضّره لكم بعناية، طازجاً كل يوم.")}</p>
        ${variants.length ? `<select class="product-variant" aria-label="اختيار الحجم أو النوع" data-variants="${product.id}">
          <option value="">اختاروا الحجم أو النوع</option>${variants.map((variant) => `<option value="${variant.id}" data-price="${variant.price_iqd ?? ""}" ${variant.price_iqd == null ? "disabled" : ""}>${esc(variant.name_ar)}${variant.price_iqd == null ? " — السعر غير محدد" : ` — ${esc(money(variant.price_iqd))}`}</option>`).join("")}
        </select>` : ""}
        <div class="product-bottom"><span class="product-price" data-price-for="${product.id}">${esc(money(initialPrice))}</span>
          <button class="add-button" data-add="${product.id}" aria-label="إضافة ${esc(product.name_ar)} إلى السلة" ${initialPrice == null && !variants.length ? "disabled" : ""}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l2.2 10.2a2 2 0 0 0 2 1.6h7.9a2 2 0 0 0 2-1.6L20.5 8H6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="9.5" cy="19" r="1.3" fill="currentColor"/><circle cx="17" cy="19" r="1.3" fill="currentColor"/></svg>
            <span>إضافة للسلة</span>
          </button>
        </div>
      </div>
    </article>`;
}

function findProduct(productId) {
  return [...state.products, ...Object.values(state.collections).flat()]
    .find((product) => String(product.id) === String(productId));
}

function openProductDetails(product) {
  const image = product.images?.[0];
  const variants = product.variants || [];
  const dialog = $("#product-dialog");
  const content = $("#product-dialog-content");
  content.innerHTML = `<div class="product-detail-layout">
    <div class="product-detail-image">${image
      ? `<img src="${esc(image)}" alt="${esc(product.name_ar)}">`
      : '<span aria-hidden="true">✳</span>'}</div>
    <div class="product-detail-copy"><span class="eyebrow eyebrow-dark">تفاصيل فينتو</span>
      <span class="product-category">${esc(product.category_name)}</span>
      <h2 id="product-dialog-title">${esc(product.name_ar)}</h2>
      <p>${esc(product.description_ar || "نحضّره لكم بعناية وبمكونات طازجة.")}</p>
      ${variants.length ? `<label class="product-detail-option">اختاروا الحجم أو النوع
        <select class="product-variant" id="detail-variant"><option value="">اختاروا الحجم أو النوع</option>
          ${variants.map((variant) => `<option value="${variant.id}" data-price="${variant.price_iqd ?? ""}" ${variant.price_iqd == null || variant.available === false ? "disabled" : ""}>${esc(variant.name_ar)}${variant.price_iqd == null ? " — السعر يحدد لاحقاً" : ` — ${esc(money(variant.price_iqd))}`}</option>`).join("")}
        </select></label>` : ""}
      <div class="product-detail-footer"><strong class="product-price" id="detail-price">${esc(money(variants.length ? null : product.price_iqd))}</strong>
        <button class="button button-primary" type="button" data-modal-add="${product.id}" ${variants.length || product.price_iqd == null ? "disabled" : ""}>أضف للسلة</button></div>
    </div></div>`;
  dialog.showModal();
}

function renderProducts() {
  const products = state.products;
  $("#menu-empty").classList.toggle("hidden", products.length > 0);
  $("#products").classList.toggle("hidden", products.length === 0);
  $("#products").innerHTML = products.map(productCard).join("");
}

function renderCategoryProductSections() {
  const container = $("#category-product-sections");
  if (!container) return;
  const categories = state.categories.length ? state.categories : [];
  const sections = categories.map((category) => {
    const products = state.products.filter((product) => String(product.category_id) === String(category.id));
    if (!products.length) return "";
    return `<section class="category-product-section" data-category-section="${category.id}">
      <div class="category-section-heading"><h2>${esc(category.name_ar)}</h2><button type="button" data-category-view="${category.id}">عرض الكل</button></div>
      <div class="product-grid category-product-grid">${products.map(productCard).join("")}</div>
    </section>`;
  }).join("");
  container.innerHTML = sections;
}

async function loadCollections() {
  const groups = ["featured", "new", "bestsellers"];
  const results = await Promise.all(groups.map(async (group) => [
    group, await api(`/api/products?group=${group}`),
  ]));
  state.collections = Object.fromEntries(results);
  const availableGroups = groups.filter((group) => state.collections[group].length);
  $("#collections").classList.toggle("hidden", availableGroups.length === 0);
  document.querySelectorAll(".collection-tab").forEach((tab) => {
    tab.classList.toggle("hidden", !availableGroups.includes(tab.dataset.group));
    tab.classList.toggle("active", tab.dataset.group === state.collectionGroup);
  });
  if (!availableGroups.includes(state.collectionGroup)) state.collectionGroup = availableGroups[0] || "featured";
  renderCollection();
}

function renderCollection() {
  const products = state.collections[state.collectionGroup] || [];
  $("#collection-products").innerHTML = products.map(productCard).join("");
  $("#collection-empty").classList.toggle("hidden", products.length > 0);
  document.querySelectorAll(".collection-tab").forEach((tab) =>
    tab.classList.toggle("active", tab.dataset.group === state.collectionGroup)
  );
}

function cartCount() {
  return state.cart.reduce((sum, item) => sum + item.quantity, 0);
}

function cartSubtotal() {
  return state.cart.reduce((sum, item) => sum + (item.lineTotal || 0), 0);
}

function renderCart() {
  $("#cart-count").textContent = cartCount().toLocaleString("ar-IQ");
  $("#mobile-cart-count").textContent = cartCount().toLocaleString("ar-IQ");
  $("#cart-subtotal").textContent = money(cartSubtotal());
  $("#checkout-button").disabled = state.cart.length === 0 || !state.storeOpen
    || !state.areas.some((area) => String(area.id) === state.selectedAreaId);
  if (!state.cart.length) {
    $("#cart-items").innerHTML = '<div class="empty-cart">سلتكم بانتظار شيء لذيذ ✳</div>';
  } else {
    $("#cart-items").innerHTML = state.cart.map((item, index) => `
      <article class="cart-item">
        <div><h3>${esc(item.name)}${item.variantName ? ` — ${esc(item.variantName)}` : ""}</h3>
          <p>${money(item.price)} للقطعة</p>
          <div class="quantity-controls">
            <button data-quantity="${index}" data-change="1" aria-label="زيادة الكمية">+</button>
            <span>${item.quantity}</span>
            <button data-quantity="${index}" data-change="-1" aria-label="تقليل الكمية">−</button>
            <button class="remove-item" data-remove="${index}" aria-label="إزالة المنتج">إزالة</button>
          </div>
        </div><strong class="cart-item-price">${money(item.lineTotal)}</strong>
      </article>`).join("");
  }
  updateDelivery();
}

async function loadCart() {
  const response = await api("/api/cart");
  state.cart = response.items;
  renderCart();
}

async function saveCart() {
  await api("/api/cart", {
    method: "PUT",
    body: JSON.stringify({ items: state.cart.map(({ productId, variantId, quantity }) => ({ productId, variantId, quantity })) }),
  });
  await loadCart();
}

function openCart() {
  $("#cart-drawer").classList.add("open");
  $("#cart-drawer").setAttribute("aria-hidden", "false");
  $("#drawer-backdrop").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeCart() {
  $("#cart-drawer").classList.remove("open");
  $("#cart-drawer").setAttribute("aria-hidden", "true");
  $("#drawer-backdrop").classList.add("hidden");
  document.body.style.overflow = "";
}

async function loadProducts() {
  const params = new URLSearchParams();
  if (state.category) params.set("category", state.category);
  if (state.search) params.set("q", state.search);
  $("#products").innerHTML = '<div class="loading-card">نحضّر لكم القائمة...</div>';
  try {
    state.products = await api(`/api/products?${params}`);
    renderProducts();
  } catch (error) {
    $("#products").innerHTML = `<div class="loading-card">${esc(error.message)}</div>`;
  }
}

async function loadAreas() {
  state.areas = await api("/api/areas");
  filterAreas();
}

function filterAreas() {
  const renderSelect = (selectId, searchId) => {
    const select = $(selectId);
    const query = $(searchId).value.trim();
    const areas = state.areas.filter((area) => area.name_ar.includes(query)
      || String(area.id) === state.selectedAreaId);
    select.innerHTML = '<option value="">اختاروا منطقة التوصيل</option>' +
      ["karkh", "rusafa"].map((district) => {
        const options = areas.filter((area) => area.district === district);
        if (!options.length) return "";
        return `<optgroup label="${district === "karkh" ? "الكرخ" : "الرصافة"}">${options.map((area) =>
          `<option value="${area.id}">${esc(area.name_ar)}${area.fee_iqd == null ? " — يحدد لاحقاً" : ` — ${esc(money(area.fee_iqd))}`}</option>`
        ).join("")}</optgroup>`;
      }).join("");
    select.value = state.selectedAreaId;
  };
  renderSelect("#area-select", "#area-search");
  renderSelect("#area-select-cart", "#area-search-cart");
  updateDelivery();
}

function updateDelivery() {
  const area = state.areas.find((item) => String(item.id) === state.selectedAreaId);
  const feeNode = $("#area-fee");
  const cartFeeNode = $("#area-fee-cart");
  const cartDelivery = $("#cart-delivery-total");
  const cartTotal = $("#cart-total");
  const delivery = $("#checkout-delivery");
  const total = $("#checkout-total");
  if (!area) {
    feeNode.textContent = "تُعرض أجرة التوصيل بعد اختيار المنطقة.";
    cartFeeNode.textContent = "اختاروا منطقة لعرض أجرة التوصيل.";
    cartDelivery.textContent = "—";
    cartTotal.textContent = "—";
    delivery.textContent = "—";
    total.textContent = "—";
    $("#checkout-button").disabled = state.cart.length === 0 || !state.storeOpen
      || !state.areas.some((item) => String(item.id) === state.selectedAreaId);
    return;
  }
  if (area.fee_iqd == null) {
    feeNode.textContent = `${area.name_ar} — أجرة التوصيل: يحدد لاحقاً.`;
    cartFeeNode.textContent = `${area.name_ar} — أجرة التوصيل: يحدد لاحقاً.`;
    cartDelivery.textContent = "يحدد لاحقاً";
    cartTotal.textContent = "يحدد لاحقاً";
    delivery.textContent = "يحدد لاحقاً";
    total.textContent = "يحدد لاحقاً";
    $("#checkout-button").disabled = state.cart.length === 0 || !state.storeOpen;
    return;
  }
  feeNode.textContent = `${area.name_ar} — أجرة التوصيل: ${money(area.fee_iqd)}`;
  cartFeeNode.textContent = `${area.name_ar} — أجرة التوصيل: ${money(area.fee_iqd)}`;
  cartDelivery.textContent = money(area.fee_iqd);
  cartTotal.textContent = money(cartSubtotal() + area.fee_iqd);
  delivery.textContent = money(area.fee_iqd);
  total.textContent = money(cartSubtotal() + area.fee_iqd);
  $("#checkout-button").disabled = state.cart.length === 0 || !state.storeOpen;
}

function renderCheckoutSummary() {
  $("#checkout-items").innerHTML = state.cart.map((item) => `
    <div class="checkout-line"><span>${esc(item.name)}${item.variantName ? ` — ${esc(item.variantName)}` : ""} × ${item.quantity}</span><strong>${money(item.lineTotal)}</strong></div>
  `).join("");
  $("#checkout-subtotal").textContent = money(cartSubtotal());
  $("#closed-note").classList.toggle("hidden", state.storeOpen);
  $("#place-order").disabled = !state.storeOpen || !state.cashPaymentEnabled || !state.cart.length
    || !state.areas.some((area) => String(area.id) === state.selectedAreaId);
  updateDelivery();
}

function renderStore(data) {
  state.storeOpen = data.isOpen;
  state.storeStatusAvailable = true;
  $("#announcement").classList.toggle("is-closed", !data.isOpen);
  $("#store-status-badge").classList.toggle("is-closed", !data.isOpen);
  $("#store-status-badge-text").textContent = data.isOpen
    ? (document.documentElement.lang === "en" ? "Open now" : "مفتوح الآن")
    : (document.documentElement.lang === "en" ? "Closed now" : "مغلق الآن");
  $("#closed-note").textContent = "المتجر مغلق الآن. يمكنكم تصفح القائمة، لكن لا يمكن تأكيد الطلب حالياً.";
  const settings = data.settings || {};
  state.cashPaymentEnabled = settings.payment_cash_enabled !== "0";
  $("#cash-disabled-note").classList.toggle("hidden", state.cashPaymentEnabled);
  $("#checkout-form").elements.namedItem("paymentMethod").options[0].disabled = !state.cashPaymentEnabled;
  $("#contact-address").textContent = settings.address || "بغداد، العراق";
  if (settings.phone) {
    $("#contact-phone").textContent = settings.phone;
    $("#contact-phone").href = `tel:${settings.phone.replace(/[^\d+]/g, "")}`;
  }
  const social = [];
  if (settings.instagram_url) social.push(`<a href="${esc(settings.instagram_url)}" target="_blank" rel="noopener noreferrer">إنستغرام</a>`);
  if (settings.facebook_url) social.push(`<a href="${esc(settings.facebook_url)}" target="_blank" rel="noopener noreferrer">فيسبوك</a>`);
  $("#social-links").innerHTML = social.join("");
  document.querySelectorAll(".hero-promotion").forEach((node) => node.remove());
  if (data.banners?.length) {
    const banner = data.banners[0];
    const heroContent = document.querySelector(".hero-content");
    const promotion = document.createElement("aside");
    promotion.className = "hero-promotion";
    if (banner.image_url) {
      const image = document.createElement("img");
      image.src = banner.image_url;
      image.alt = "";
      image.loading = "lazy";
      promotion.append(image);
    }
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = banner.title_ar;
    copy.append(title);
    if (banner.description_ar) {
      const description = document.createElement("span");
      description.textContent = banner.description_ar;
      copy.append(description);
    }
    promotion.append(copy);
    heroContent.prepend(promotion);
  }
  renderCart();
  if ($("#checkout-dialog").open) renderCheckoutSummary();
}

let searchTimer;

function applyLanguage(language) {
  const isEnglish = language === "en";
  document.documentElement.lang = isEnglish ? "en" : "ar";
  document.documentElement.dir = isEnglish ? "ltr" : "rtl";
  localStorage.setItem("venito-language", language);
  $("#language-toggle").textContent = isEnglish ? "ع" : "EN";
  $("#language-toggle").setAttribute("aria-label", isEnglish ? "Switch to Arabic" : "Switch to English");
  $("#product-search").placeholder = isEnglish ? "What are you craving?" : "شنو تحب تطلب اليوم؟";
  $("#open-cart").querySelector("span:nth-child(2)").textContent = isEnglish ? "Cart" : "السلة";
  $("#open-cart").setAttribute("aria-label", isEnglish ? "Shopping cart" : "سلة التسوق");
  $("#order-now-label").textContent = isEnglish ? "Order now" : "اطلب هسه";
  $("#notification-view-cart").textContent = isEnglish ? "View cart" : "عرض السلة";
  document.querySelectorAll("#main-nav a").forEach((link, index) => {
    link.textContent = isEnglish
      ? ["Home", "Menu", "Our story", "Contact us"][index]
      : ["الرئيسية", "قائمة الطعام", "حكايتنا", "تواصل معنا"][index];
  });
  const heroHeading = document.querySelector(".hero h1");
  const heroText = document.querySelector(".hero-content > p");
  if (isEnglish) {
    heroHeading.innerHTML = "What are you craving?<br>Make it <em>sweet</em>";
    heroText.textContent = "Fresh cakes, pastries and sweets, made with care in Baghdad.";
  } else {
    heroHeading.innerHTML = "شنو تحبون تطلبون؟<br>لحظتكم <em>أحلى ويانا</em>";
    heroText.textContent = "كيك ومعجنات وحلويات طازجة، نحضّرها بعناية حتى تجمعكم على طعم تحبّوه.";
  }
  const menuButton = document.querySelector(".hero-actions .button-light");
  if (menuButton) menuButton.innerHTML = isEnglish ? "Explore our menu <span>←</span>" : "تسوّقوا هسه <span>←</span>";
  if (state.storeStatusAvailable) {
    $("#store-status-badge-text").textContent = state.storeOpen
      ? (isEnglish ? "Open now" : "مفتوح الآن")
      : (isEnglish ? "Closed now" : "مغلق الآن");
  }
}

function markStoreStatusUnavailable() {
  state.storeOpen = false;
  state.storeStatusAvailable = false;
  $("#announcement").classList.add("is-closed");
  $("#store-status-badge").classList.remove("is-closed");
  $("#store-status-badge-text").textContent = "تعذر التحقق من الحالة";
  $("#closed-note").textContent = "تعذر التحقق من حالة المتجر. يرجى المحاولة لاحقاً.";
  $("#closed-note").classList.remove("hidden");
  renderCart();
  if ($("#checkout-dialog").open) renderCheckoutSummary();
}

async function init() {
  $("#year").textContent = new Date().getFullYear();
  const savedTheme = localStorage.getItem("venito-theme") || "light";
  document.documentElement.dataset.theme = savedTheme;
  $("#theme-toggle").setAttribute("aria-pressed", String(savedTheme === "dark"));
  $("#theme-toggle").setAttribute("aria-label", savedTheme === "dark" ? "تفعيل الوضع النهاري" : "تفعيل الوضع الليلي");
  $("#theme-toggle").innerHTML = `<span aria-hidden="true">${savedTheme === "dark" ? "☀" : "☾"}</span>`;
  applyLanguage(localStorage.getItem("venito-language") === "en" ? "en" : "ar");
  try {
    renderStore(await api("/api/store"));
  } catch (error) {
    toast(error.message);
    markStoreStatusUnavailable();
  }
  try {
    state.categories = await api("/api/categories");
    renderCategories();
    await Promise.all([loadProducts(), loadCart(), loadAreas(), loadCollections()]);
    renderCategoryProductSections();
  } catch (error) {
    toast(error.message);
  }

  $("#categories").addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.category = button.dataset.category;
    renderCategories();
    loadProducts();
    $("#menu").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  $("#collection-tabs").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-group]");
    if (!tab || tab.classList.contains("hidden")) return;
    state.collectionGroup = tab.dataset.group;
    renderCollection();
  });

  const productGrids = [$("#products"), $("#collection-products")];
  $("#product-dialog-content").addEventListener("change", (event) => {
    if (event.target.id !== "detail-variant") return;
    const option = event.target.selectedOptions[0];
    const price = option?.dataset.price;
    $("#detail-price").textContent = price ? money(Number(price)) : "اختاروا الحجم";
    $("#product-dialog-content [data-modal-add]").disabled = !price;
  });

  async function addToCart(selectedProduct, variantId = null) {
    if (selectedProduct.variants?.length && !variantId) return toast("اختاروا الحجم أو النوع أولاً.");
    if (!state.storeOpen) return toast("المتجر مغلق الآن، ولا يمكن تأكيد الطلب.");
    const key = `${selectedProduct.id}:${variantId || ""}`;
    const existing = state.cart.find((item) => `${item.productId}:${item.variantId || ""}` === key);
    if (existing) existing.quantity = Math.min(99, existing.quantity + 1);
    else {
      const variant = selectedProduct.variants?.find((item) => item.id === variantId);
      const price = variant ? variant.price_iqd : selectedProduct.price_iqd;
      if (price == null) return toast("لم يحدد المتجر سعر هذا المنتج بعد.");
      state.cart.push({
        productId: selectedProduct.id, variantId, name: selectedProduct.name_ar,
        variantName: variant?.name_ar || "", price, quantity: 1, lineTotal: price,
      });
    }
    renderCart();
    try {
      await saveCart();
      const message = document.documentElement.lang === "en"
        ? `${selectedProduct.name_ar} was added to the cart successfully`
        : `انضاف ${selectedProduct.name_ar} للسلة`;
      showNotification(message);
      return true;
    } catch (error) {
      toast(error.message);
      return false;
    }
  }

  productGrids.forEach((grid) => grid.addEventListener("change", (event) => {
    const select = event.target.closest("[data-variants]");
    if (!select) return;
    const option = select.selectedOptions[0];
    const price = option?.dataset.price;
    const productId = select.dataset.variants;
    const card = select.closest(".product-card");
    const priceNode = card.querySelector(`[data-price-for="${productId}"]`);
    const button = card.querySelector(`[data-add="${productId}"]`);
    priceNode.textContent = price ? money(Number(price)) : "اختاروا حجماً";
    button.disabled = !price;
  }));
  productGrids.forEach((grid) => grid.addEventListener("error", (event) => {
    if (event.target instanceof HTMLImageElement) {
      event.target.hidden = true;
      event.target.nextElementSibling?.removeAttribute("hidden");
    }
  }, true));

  async function addProductFromGrid(event) {
    const favorite = event.target.closest("[data-favorite]");
    if (favorite) {
      favorite.classList.toggle("active");
      favorite.textContent = favorite.classList.contains("active") ? "♥" : "♡";
      return;
    }
    const detailsButton = event.target.closest("[data-details]");
    if (detailsButton) {
      const product = findProduct(detailsButton.dataset.details);
      if (product) openProductDetails(product);
      return;
    }
    const button = event.target.closest("[data-add]");
    if (!button) return;
    const selectedProduct = findProduct(button.dataset.add);
    if (!selectedProduct) return;
    const variantSelect = button.closest(".product-card").querySelector(`[data-variants="${selectedProduct.id}"]`);
    const variantId = variantSelect?.value ? Number(variantSelect.value) : null;
    addToCart(selectedProduct, variantId);
  }
  productGrids.forEach((grid) => grid.addEventListener("click", addProductFromGrid));
  $("#product-dialog-content").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-modal-add]");
    if (!button) return;
    const product = findProduct(button.dataset.modalAdd);
    if (!product) return;
    const variantId = $("#detail-variant")?.value ? Number($("#detail-variant").value) : null;
    button.disabled = true;
    if (await addToCart(product, variantId)) $("#product-dialog").close();
    else button.disabled = false;
  });

  const runSearch = () => {
    clearTimeout(searchTimer);
    state.search = $("#product-search").value.trim();
    loadProducts();
    $("#menu").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("#product-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 250);
  });
  $("#search-button")?.addEventListener("click", runSearch);
  $("#hero-choose-location")?.addEventListener("click", () => $("#delivery-dialog").showModal());
  $("#open-cart").addEventListener("click", openCart);
  $("#category-product-sections")?.addEventListener("click", (event) => {
    const viewButton = event.target.closest("[data-category-view]");
    if (viewButton) {
      state.category = viewButton.dataset.categoryView;
      renderCategories();
      loadProducts();
      $("#menu").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  $("#category-product-sections")?.addEventListener("click", (event) => {
    const favorite = event.target.closest("[data-favorite]");
    if (!favorite) return;
    favorite.classList.toggle("active");
    favorite.textContent = favorite.classList.contains("active") ? "♥" : "♡";
  });
  $("#open-account-page")?.addEventListener("click", () => $("#account-dialog").showModal());
  $("#close-account")?.addEventListener("click", () => $("#account-dialog").close());
  $("#open-delivery-modal")?.addEventListener("click", () => $("#delivery-dialog").showModal());
  $("#close-delivery")?.addEventListener("click", () => $("#delivery-dialog").close());
  $("#floating-top")?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  $("#floating-whatsapp")?.addEventListener("click", () => window.open("https://wa.me/9647722236815", "_blank", "noopener,noreferrer"));
  document.querySelectorAll(".delivery-option").forEach((option) => option.addEventListener("change", () => {
    document.querySelectorAll(".delivery-option").forEach((item) => item.classList.remove("selected"));
    option.classList.add("selected");
  }));
  document.querySelector(".delivery-map")?.addEventListener("click", () => {
    const mapText = document.querySelector(".delivery-map strong");
    if (!navigator.geolocation) {
      toast("تحديد الموقع الجغرافي غير متاح على هذا الجهاز");
      return;
    }
    navigator.geolocation.getCurrentPosition(() => {
      mapText.textContent = "تم تحديد موقعك الحالي";
      $("#delivery-confirm").textContent = "تم تحديد الموقع ✓";
    }, () => toast("يرجى السماح للمتصفح بتحديد موقعك"), { enableHighAccuracy: true, timeout: 10000 });
  });
  $("#delivery-save")?.addEventListener("click", () => {
    const locationText = "بغداد - حي أور";
    $(".market-location-copy strong").textContent = locationText;
    localStorage.setItem("venito_delivery_location", locationText);
    $("#delivery-dialog").close();
    toast("تم حفظ موقع التوصيل");
  });
  $("#mobile-open-cart").addEventListener("click", openCart);
  $("#account-language")?.addEventListener("click", () => applyLanguage(document.documentElement.lang === "ar" ? "en" : "ar"));
  $("#language-toggle").addEventListener("click", () => {
    applyLanguage(document.documentElement.lang === "ar" ? "en" : "ar");
  });
  $("#theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("venito-theme", dark ? "dark" : "light");
    $("#theme-toggle").setAttribute("aria-pressed", String(dark));
    $("#theme-toggle").setAttribute("aria-label", dark ? "تفعيل الوضع النهاري" : "تفعيل الوضع الليلي");
    $("#theme-toggle").innerHTML = `<span aria-hidden="true">${dark ? "☀" : "☾"}</span>`;
  });
  $("#order-now").addEventListener("click", () => {
    if (cartCount() === 0) {
      document.querySelector("#menu").scrollIntoView({ behavior: "smooth" });
      toast(document.documentElement.lang === "en" ? "Choose something delicious." : "اختاروا شيئاً لذيذاً.");
    } else {
      openCart();
    }
  });
  $("#notification-view-cart").addEventListener("click", () => {
    $("#notification-island").classList.remove("visible");
    $("#notification-island").setAttribute("aria-hidden", "true");
    openCart();
  });
  $("#close-cart").addEventListener("click", closeCart);
  $("#drawer-backdrop").addEventListener("click", closeCart);
  $("#cart-items").addEventListener("click", async (event) => {
    const remove = event.target.closest("[data-remove]");
    const change = event.target.closest("[data-quantity]");
    if (!remove && !change) return;
    const index = Number((remove || change).dataset.remove ?? (remove || change).dataset.quantity);
    if (!state.cart[index]) return;
    if (remove) state.cart.splice(index, 1);
    else {
      state.cart[index].quantity += Number(change.dataset.change);
      if (state.cart[index].quantity <= 0) state.cart.splice(index, 1);
    }
    renderCart();
    try {
      await saveCart();
      renderCheckoutSummary();
    } catch (error) {
      toast(error.message);
    }
  });

  $("#checkout-button").addEventListener("click", async () => {
    if (!state.storeOpen) return toast("المتجر مغلق الآن.");
    try {
      await loadAreas();
      renderCheckoutSummary();
      closeCart();
      $("#checkout-dialog").showModal();
    } catch (error) {
      toast(error.message);
    }
  });
  $("#area-search").addEventListener("input", filterAreas);
  $("#area-search-cart").addEventListener("input", filterAreas);
  const selectArea = (event) => {
    state.selectedAreaId = event.currentTarget.value;
    if (state.selectedAreaId) localStorage.setItem("venito_delivery_area", state.selectedAreaId);
    else localStorage.removeItem("venito_delivery_area");
    filterAreas();
    renderCart();
    renderCheckoutSummary();
  };
  $("#area-select").addEventListener("change", selectArea);
  $("#area-select-cart").addEventListener("change", selectArea);
  $("#checkout-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload = Object.fromEntries(values.entries());
    payload.areaId = Number(payload.areaId);
    const area = state.areas.find((item) => item.id === payload.areaId);
    if (!area) return toast("اختاروا منطقة توصيل فعالة.");
    const submit = $("#place-order");
    submit.disabled = true;
    submit.textContent = "جارٍ تأكيد الطلب...";
    $("#checkout-error").classList.add("hidden");
    try {
      const order = await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });
      $("#checkout-dialog").close();
      $("#confirmed-order-number").textContent = order.orderNumber;
      currentReceiptUrl = order.receiptUrl;
      const receiptDownload = $("#receipt-download");
      receiptDownload.href = currentReceiptUrl;
      receiptDownload.download = `VENTO-${order.receiptNumber}.pdf`;
      receiptDownload.hidden = !currentReceiptUrl;
      $("#share-receipt").hidden = !currentReceiptUrl;
      $("#success-delivery-note").textContent = order.deliveryFeeDetermined
        ? "الدفع نقداً عند الاستلام. سنتواصل معكم لتأكيد التفاصيل."
        : "تم استلام طلبكم. أجرة التوصيل لهذه المنطقة يحدد لاحقاً، وسنتواصل معكم قبل التسليم.";
      $("#success-dialog").showModal();
      await loadCart();
      renderCart();
      form.reset();
      state.selectedAreaId = "";
      localStorage.removeItem("venito_delivery_area");
      $("#area-search").value = "";
      $("#area-search-cart").value = "";
      filterAreas();
    } catch (error) {
      $("#checkout-error").textContent = error.message;
      $("#checkout-error").classList.remove("hidden");
    } finally {
      submit.disabled = !state.storeOpen || !state.cashPaymentEnabled || !state.cart.length
        || !state.areas.some((area) => String(area.id) === state.selectedAreaId);
      submit.innerHTML = 'تأكيد الطلب <span>←</span>';
    }
  });
  $("#share-receipt").addEventListener("click", async () => {
    if (!currentReceiptUrl) return;
    try {
      if (navigator.share && typeof File !== "undefined") {
        const response = await fetch(currentReceiptUrl, { credentials: "same-origin" });
        if (!response.ok) throw new Error("تعذر تحميل الإيصال لمشاركته.");
        const file = new File([await response.blob()], $("#receipt-download").download, {
          type: "application/pdf",
        });
        if (navigator.canShare?.({ files: [file] })) {
          await navigator.share({ files: [file], title: "إيصال طلب VENTO" });
          return;
        }
      }
      if (navigator.share) {
        await navigator.share({
          title: "إيصال طلب VENTO",
          url: new URL(currentReceiptUrl, window.location.origin).href,
        });
      } else {
        toast("نزّلوا الإيصال PDF ثم شاركوه من الهاتف.");
      }
    } catch (error) {
      if (error.name !== "AbortError") toast(error.message);
    }
  });
  $("#success-done").addEventListener("click", () => $("#success-dialog").close());
  $("#mobile-menu-toggle").addEventListener("click", () => {
    const nav = $("#main-nav");
    const open = nav.classList.toggle("open");
    $("#mobile-menu-toggle").setAttribute("aria-expanded", String(open));
  });
  $("#main-nav").addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      $("#main-nav").classList.remove("open");
      $("#mobile-menu-toggle").setAttribute("aria-expanded", "false");
    }
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 820) {
      $("#main-nav").classList.remove("open");
      $("#mobile-menu-toggle").setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeCart();
  });
  const refreshStoreStatus = async () => {
    try {
      renderStore(await api("/api/store"));
    } catch (error) {
      markStoreStatusUnavailable();
      console.error("تعذر تحديث حالة المتجر:", error);
    }
  };
  window.setInterval(refreshStoreStatus, 30_000);
  window.setInterval(async () => {
    try {
      await loadCollections();
    } catch (error) {
      console.error("تعذر تحديث المنتجات المميزة:", error);
    }
  }, 60_000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshStoreStatus();
  });
  window.addEventListener("focus", refreshStoreStatus);
}

init();
