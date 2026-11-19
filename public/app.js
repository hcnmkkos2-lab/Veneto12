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
  cashPaymentEnabled: true,
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

function renderCategories() {
  const all = `<button class="category-chip ${state.category === "" ? "active" : ""}" data-category="">الكل</button>`;
  $("#categories").innerHTML = all + state.categories.map((category) =>
    `<button class="category-chip ${state.category === String(category.id) ? "active" : ""}" data-category="${category.id}">${esc(category.name_ar)}</button>`
  ).join("");
}

function productCard(product) {
  const image = product.images?.[0];
  const variants = product.variants || [];
  const initialPrice = variants.length ? null : product.price_iqd;
  return `<article class="product-card">
      <div class="product-image">${image
        ? `<img src="${esc(image)}" alt="${esc(product.name_ar)}" loading="lazy"><div class="product-placeholder" hidden>✳</div>`
        : `<div class="product-placeholder" aria-hidden="true">✳</div>`}
        ${product.is_new ? '<span class="product-badge">جديد</span>' : product.featured ? '<span class="product-badge">اختيار فينيتو</span>' : ""}
      </div>
      <div class="product-info">
        <h3>${esc(product.name_ar)}</h3><span class="product-category">${esc(product.category_name)}</span>
        <p class="product-description">${esc(product.description_ar || "نحضّره لكم بعناية، طازجاً كل يوم.")}</p>
        ${variants.length ? `<select class="product-variant" aria-label="اختيار الحجم أو النوع" data-variants="${product.id}">
          <option value="">اختاروا الحجم أو النوع</option>${variants.map((variant) => `<option value="${variant.id}" data-price="${variant.price_iqd ?? ""}" ${variant.price_iqd == null ? "disabled" : ""}>${esc(variant.name_ar)}${variant.price_iqd == null ? " — السعر غير محدد" : ` — ${esc(money(variant.price_iqd))}`}</option>`).join("")}
        </select>` : ""}
        <div class="product-bottom"><span class="product-price" data-price-for="${product.id}">${esc(money(initialPrice))}</span>
          <button class="add-button" data-add="${product.id}" aria-label="إضافة ${esc(product.name_ar)} إلى السلة" ${initialPrice == null && !variants.length ? "disabled" : ""}>+</button>
        </div>
      </div>
    </article>`;
}

function renderProducts() {
  const products = state.products;
  $("#menu-empty").classList.toggle("hidden", products.length > 0);
  $("#products").classList.toggle("hidden", products.length === 0);
  $("#products").innerHTML = products.map(productCard).join("");
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
  $("#cart-subtotal").textContent = money(cartSubtotal());
  $("#checkout-button").disabled = state.cart.length === 0 || !state.storeOpen;
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
  const select = $("#area-select");
  const query = $("#area-search").value.trim();
  const selected = select.value;
  const areas = state.areas.filter((area) => area.name_ar.includes(query));
  select.innerHTML = '<option value="">اختاروا منطقة التوصيل</option>' +
    ["karkh", "rusafa"].map((district) => {
      const options = areas.filter((area) => area.district === district);
      if (!options.length) return "";
      return `<optgroup label="${district === "karkh" ? "الكرخ" : "الرصافة"}">${options.map((area) =>
        `<option value="${area.id}" data-fee="${area.fee_iqd ?? ""}">${esc(area.name_ar)}${area.fee_iqd == null ? " — أجرة التوصيل غير محددة" : ""}</option>`
      ).join("")}</optgroup>`;
    }).join("");
  if (selected && areas.some((area) => String(area.id) === selected)) select.value = selected;
  updateDelivery();
}

function updateDelivery() {
  const select = $("#area-select");
  const area = state.areas.find((item) => String(item.id) === select.value);
  const feeNode = $("#area-fee");
  const delivery = $("#checkout-delivery");
  const total = $("#checkout-total");
  if (!area) {
    feeNode.textContent = "تُعرض أجرة التوصيل بعد اختيار المنطقة.";
    delivery.textContent = "—";
    total.textContent = "—";
    return;
  }
  if (area.fee_iqd == null) {
    feeNode.textContent = "لم تُحدد أجرة التوصيل لهذه المنطقة. اختاروا منطقة أخرى.";
    delivery.textContent = "غير محددة";
    total.textContent = "—";
    return;
  }
  feeNode.textContent = `أجرة التوصيل: ${money(area.fee_iqd)}`;
  delivery.textContent = money(area.fee_iqd);
  total.textContent = money(cartSubtotal() + area.fee_iqd);
}

function renderCheckoutSummary() {
  $("#checkout-items").innerHTML = state.cart.map((item) => `
    <div class="checkout-line"><span>${esc(item.name)}${item.variantName ? ` — ${esc(item.variantName)}` : ""} × ${item.quantity}</span><strong>${money(item.lineTotal)}</strong></div>
  `).join("");
  $("#checkout-subtotal").textContent = money(cartSubtotal());
  $("#closed-note").classList.toggle("hidden", state.storeOpen);
  $("#place-order").disabled = !state.storeOpen || !state.cashPaymentEnabled || !state.cart.length;
  updateDelivery();
}

function renderStore(data) {
  state.storeOpen = data.isOpen;
  const status = $("#store-status");
  status.textContent = data.storeStatus;
  $("#announcement").classList.toggle("is-closed", !data.isOpen);
  $("#store-status-badge").classList.toggle("is-closed", !data.isOpen);
  $("#store-status-badge-text").textContent = data.isOpen
    ? (document.documentElement.lang === "en" ? "Open now" : "مفتوح الآن")
    : (document.documentElement.lang === "en" ? "Closed now" : "مغلق الآن");
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
  $("#product-search").placeholder = isEnglish ? "What are you craving?" : "ماذا تشتهي؟";
  $("#open-cart").querySelector("span:nth-child(2)").textContent = isEnglish ? "Cart" : "السلة";
  $("#open-cart").setAttribute("aria-label", isEnglish ? "Shopping cart" : "سلة التسوق");
  $("#order-now-label").textContent = isEnglish ? "Order now" : "اطلب الآن";
  $("#notification-view-cart").textContent = isEnglish ? "View cart" : "عرض السلة";
  document.querySelectorAll("#main-nav a").forEach((link, index) => {
    link.textContent = isEnglish
      ? ["Home", "Menu", "Our story", "Contact us"][index]
      : ["الرئيسية", "قائمة الطعام", "حكايتنا", "تواصل معنا"][index];
  });
  const heroHeading = document.querySelector(".hero h1");
  const heroText = document.querySelector(".hero-content > p");
  if (isEnglish) {
    heroHeading.innerHTML = "Sweet moments<br>start <em>here</em>";
    heroText.textContent = "From the first creamy layer to the last crumb... we make every piece with love.";
  } else {
    heroHeading.innerHTML = "لحظاتكم الحلوة<br>تبدأ <em>من هنا</em>";
    heroText.textContent = "من أول طبقة كريمة إلى آخر فتاتة... نصنع كل قطعة بحب لتكون ذكرى لا تُنسى.";
  }
  const menuButton = document.querySelector(".hero-actions .button-light");
  if (menuButton) menuButton.innerHTML = isEnglish ? "Explore our menu <span>←</span>" : "اكتشفوا قائمتنا <span>←</span>";
  renderStoreFromCurrentState();
}

async function renderStoreFromCurrentState() {
  try {
    renderStore(await api("/api/store"));
  } catch (_) {}
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
    const [store, categories] = await Promise.all([api("/api/store"), api("/api/categories")]);
    renderStore(store);
    state.categories = categories;
    renderCategories();
    await Promise.all([loadProducts(), loadCart(), loadAreas(), loadCollections()]);
  } catch (error) {
    toast(error.message);
  }

  $("#categories").addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.category = button.dataset.category;
    renderCategories();
    loadProducts();
  });

  $("#collection-tabs").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-group]");
    if (!tab || tab.classList.contains("hidden")) return;
    state.collectionGroup = tab.dataset.group;
    renderCollection();
  });

  const productGrids = [$("#products"), $("#collection-products")];
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
    const button = event.target.closest("[data-add]");
    if (!button) return;
    const product = state.products.find((item) => String(item.id) === button.dataset.add);
    const collectionProduct = Object.values(state.collections).flat().find((item) => String(item.id) === button.dataset.add);
    const selectedProduct = product || collectionProduct;
    if (!selectedProduct) return;
    const variantSelect = button.closest(".product-card").querySelector(`[data-variants="${selectedProduct.id}"]`);
    const variantId = variantSelect?.value ? Number(variantSelect.value) : null;
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
    try {
      await saveCart();
      const message = document.documentElement.lang === "en"
        ? `${selectedProduct.name_ar} was added to the cart successfully`
        : `تمت إضافة ${selectedProduct.name_ar} إلى السلة بنجاح`;
      showNotification(message);
    } catch (error) {
      toast(error.message);
    }
  }
  productGrids.forEach((grid) => grid.addEventListener("click", addProductFromGrid));

  $("#product-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = $("#product-search").value.trim();
      loadProducts();
    }, 250);
  });
  $("#open-cart").addEventListener("click", openCart);
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
  $("#area-select").addEventListener("change", updateDelivery);
  $("#checkout-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload = Object.fromEntries(values.entries());
    payload.areaId = Number(payload.areaId);
    const area = state.areas.find((item) => item.id === payload.areaId);
    if (!area || area.fee_iqd == null) return toast("اختاروا منطقة توصيل فعالة برسوم محددة.");
    const submit = $("#place-order");
    submit.disabled = true;
    submit.textContent = "جارٍ تأكيد الطلب...";
    $("#checkout-error").classList.add("hidden");
    try {
      const order = await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });
      $("#checkout-dialog").close();
      $("#confirmed-order-number").textContent = order.orderNumber;
      $("#success-dialog").showModal();
      await loadCart();
      renderCart();
      form.reset();
      $("#area-search").value = "";
      filterAreas();
    } catch (error) {
      $("#checkout-error").textContent = error.message;
      $("#checkout-error").classList.remove("hidden");
    } finally {
      submit.disabled = !state.storeOpen || !state.cashPaymentEnabled;
      submit.innerHTML = 'تأكيد الطلب <span>←</span>';
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
  window.setInterval(async () => {
    try {
      renderStore(await api("/api/store"));
      await loadCollections();
    } catch (error) {
      toast(`تعذر تحديث حالة المتجر: ${error.message}`);
    }
  }, 60_000);
}

init();
