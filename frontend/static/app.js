const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

const state = {
  users: [],
  products: [],
  orders: [],
  cart: loadCart(),
  customerId: sessionStorage.getItem("stride-customer") || "",
  orderFilter: "",
  brand: "",
  category: "",
  services: {},
};

const els = {
  productList: document.querySelector("#product-list"),
  brandFilters: document.querySelector("#brand-filters"),
  brandList: document.querySelector("#brand-list"),
  categoryFilter: document.querySelector("#category-filter"),
  cartLines: document.querySelector("#cart-lines"),
  cartTotal: document.querySelector("#cart-total"),
  placeOrder: document.querySelector("#place-order"),
  customerSelect: document.querySelector("#customer-select"),
  orderFilter: document.querySelector("#order-filter"),
  orderList: document.querySelector("#order-list"),
  userList: document.querySelector("#user-list"),
  serviceStatus: document.querySelector("#service-status"),
  toast: document.querySelector("#toast"),
};

function loadCart() {
  try {
    const saved = JSON.parse(localStorage.getItem("stride-cart") || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

function saveCart() {
  localStorage.setItem("stride-cart", JSON.stringify(state.cart));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function initials(brand) {
  return brand
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || "")
    .join("")
    .toUpperCase();
}

function brandTone(brand) {
  const tones = ["#1c1c1c", "#9c3d24", "#1f4b3a", "#234e70", "#6b3f2a", "#3d3a34"];
  let hash = 0;
  for (const char of brand) hash = (hash + char.charCodeAt(0)) % tones.length;
  return tones[hash];
}

function shoeLabel(item) {
  return `${item.brand} ${item.name}`.trim();
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => els.toast.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function showView(name) {
  for (const view of ["shop", "orders", "customers"]) {
    document.querySelector(`#view-${view}`).hidden = view !== name;
    document.querySelector(`[data-view="${view}"]`).classList.toggle("active", view === name);
  }
}

function visibleProducts() {
  return state.products.filter((product) => {
    const brandOk = !state.brand || product.brand === state.brand;
    const categoryOk = !state.category || product.category === state.category;
    return brandOk && categoryOk;
  });
}

function fillCustomerSelects() {
  const options = state.users
    .map((user) => `<option value="${user.id}">${escapeHtml(user.name)}</option>`)
    .join("");
  els.customerSelect.innerHTML = `<option value="">Choose a customer</option>${options}`;
  els.orderFilter.innerHTML = `<option value="">All customers</option>${options}`;
  els.customerSelect.value = state.users.some((user) => String(user.id) === state.customerId)
    ? state.customerId
    : "";
  state.customerId = els.customerSelect.value;
  els.orderFilter.value = state.orderFilter;
}

function renderFilters() {
  const brands = [...new Set(state.products.map((product) => product.brand))].sort();
  const chips = ["", ...brands]
    .map((brand) => {
      const label = brand || "All brands";
      const active = state.brand === brand ? "active" : "";
      return `<button type="button" class="chip ${active}" data-brand="${escapeHtml(brand)}">${escapeHtml(label)}</button>`;
    })
    .join("");
  els.brandFilters.innerHTML = chips;
  els.brandList.innerHTML = brands.map((brand) => `<option value="${escapeHtml(brand)}"></option>`).join("");
}

function renderStatus() {
  const labels = [
    ["users", "User"],
    ["products", "Product"],
    ["orders", "Order"],
  ];
  els.serviceStatus.innerHTML = labels
    .map(([key, label]) => {
      const up = state.services[key];
      const cls = up === true ? "up" : up === false ? "down" : "";
      return `<span><i class="dot ${cls}"></i>${label}</span>`;
    })
    .join("");
}

function renderProducts() {
  const products = visibleProducts();
  if (!products.length) {
    els.productList.innerHTML = `<p class="empty">No shoes match this filter.</p>`;
    return;
  }
  els.productList.innerHTML = products
    .map((product) => {
      const stockClass = product.stock === 0 ? "out" : product.stock < 5 ? "low" : "";
      const stockLabel = product.stock === 0 ? "Out of stock" : `${product.stock} in stock`;
      return `
        <article class="card product">
          <div class="swatch" style="background:${brandTone(product.brand)}">${escapeHtml(initials(product.brand))}</div>
          <p class="brand-name">${escapeHtml(product.brand)}</p>
          <h3>${escapeHtml(product.name)}</h3>
          <p>${escapeHtml(product.description || "No description")}</p>
          <p class="specs">${escapeHtml(product.category)} · US ${escapeHtml(product.size)} · ${escapeHtml(product.color)}</p>
          <div class="meta">
            <strong class="price">${money.format(product.price)}</strong>
            <span class="stock ${stockClass}">${stockLabel}</span>
          </div>
          <div class="qty-row">
            <input id="qty-${product.id}" type="number" min="1" max="${product.stock}" value="1" aria-label="Quantity for ${escapeHtml(shoeLabel(product))}" ${product.stock === 0 ? "disabled" : ""}>
            <button type="button" data-action="add-cart" data-id="${product.id}" ${product.stock === 0 ? "disabled" : ""}>Add</button>
          </div>
          <div class="card-actions">
            <button type="button" class="ghost" data-action="edit-product" data-id="${product.id}">Edit</button>
            <button type="button" class="danger" data-action="delete-product" data-id="${product.id}">Delete</button>
          </div>
        </article>`;
    })
    .join("");
}

function renderCart() {
  if (!state.cart.length) {
    els.cartLines.innerHTML = `<p class="empty">No shoes selected.</p>`;
  } else {
    els.cartLines.innerHTML = state.cart
      .map(
        (item) => `
          <div class="line">
            <span>${item.quantity} × ${escapeHtml(shoeLabel(item))}<br><small>US ${escapeHtml(item.size)} · ${escapeHtml(item.color)}</small></span>
            <span>
              ${money.format(item.price * item.quantity)}
              <button type="button" class="ghost" data-action="remove-cart" data-id="${item.productId}" aria-label="Remove ${escapeHtml(shoeLabel(item))}">×</button>
            </span>
          </div>`
      )
      .join("");
  }
  const total = state.cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
  els.cartTotal.textContent = money.format(total);
  els.placeOrder.disabled = !state.cart.length || !state.customerId;
}

function renderOrders() {
  const filtered = state.orders.filter(
    (order) => !state.orderFilter || String(order.user_id) === state.orderFilter
  );
  if (!filtered.length) {
    els.orderList.innerHTML = `<p class="empty">No orders to show.</p>`;
    return;
  }
  els.orderList.innerHTML = filtered
    .map((order) => {
      const when = new Date(order.created_at).toLocaleString();
      const items = order.items
        .map(
          (item) =>
            `<li>${item.quantity} × ${escapeHtml(item.brand)} ${escapeHtml(item.product_name)} · US ${escapeHtml(item.size)} · ${escapeHtml(item.color)}</li>`
        )
        .join("");
      const cancel =
        order.status === "created"
          ? `<button type="button" data-action="cancel-order" data-id="${order.id}">Cancel order</button>`
          : "";
      return `
        <article class="order">
          <div class="order-head">
            <h3>Order #${order.id}</h3>
            <span class="badge ${order.status === "cancelled" ? "cancelled" : ""}">${escapeHtml(order.status)}</span>
          </div>
          <p>${escapeHtml(order.user_name)} · ${escapeHtml(order.user_email)}</p>
          <ul>${items}</ul>
          <div class="order-actions">
            <strong>${money.format(order.total)}</strong>
            <span class="muted">${escapeHtml(when)}</span>
          </div>
          ${cancel}
        </article>`;
    })
    .join("");
}

function renderUsers() {
  if (!state.users.length) {
    els.userList.innerHTML = `<p class="empty">No customers yet.</p>`;
    return;
  }
  els.userList.innerHTML = state.users
    .map(
      (user) => `
        <article class="order">
          <div class="order-head">
            <h3>${escapeHtml(user.name)}</h3>
            <span class="muted">#${user.id}</span>
          </div>
          <p>${escapeHtml(user.email)}</p>
          <div class="card-actions">
            <button type="button" class="ghost" data-action="edit-user" data-id="${user.id}">Edit</button>
            <button type="button" class="danger" data-action="delete-user" data-id="${user.id}">Delete</button>
          </div>
        </article>`
    )
    .join("");
}

function syncCartWithProducts() {
  state.cart = state.cart
    .map((item) => {
      const product = state.products.find((entry) => entry.id === item.productId);
      if (!product || product.stock < 1) return null;
      return {
        productId: product.id,
        brand: product.brand,
        name: product.name,
        size: product.size,
        color: product.color,
        price: product.price,
        quantity: Math.min(item.quantity, product.stock),
      };
    })
    .filter(Boolean);
  saveCart();
}

async function refresh() {
  const [users, products, orders, health] = await Promise.allSettled([
    api("/api/users"),
    api("/api/products"),
    api("/api/orders"),
    fetch("/api/health").then(async (response) => {
      const body = await response.json().catch(() => ({}));
      return body.services || {};
    }),
  ]);

  if (users.status === "fulfilled") state.users = users.value;
  if (products.status === "fulfilled") state.products = products.value;
  if (orders.status === "fulfilled") state.orders = [...orders.value].reverse();
  state.services = health.status === "fulfilled" ? health.value : {};

  if (products.status === "fulfilled") syncCartWithProducts();
  fillCustomerSelects();
  renderStatus();
  renderFilters();
  renderProducts();
  renderCart();
  renderOrders();
  renderUsers();

  const failed = [users, products, orders].find((result) => result.status === "rejected");
  if (failed) toast(failed.reason.message);
}

function resetProductForm() {
  document.querySelector("#product-form").reset();
  document.querySelector("#product-id").value = "";
  document.querySelector("#product-form-title").textContent = "Add a shoe";
  document.querySelector("#product-submit").textContent = "Add shoe";
  document.querySelector("#product-cancel").hidden = true;
}

function resetUserForm() {
  document.querySelector("#user-form").reset();
  document.querySelector("#user-id").value = "";
  document.querySelector("#user-form-title").textContent = "Add a customer";
  document.querySelector("#user-submit").textContent = "Add customer";
  document.querySelector("#user-cancel").hidden = true;
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

document.querySelector("#refresh").addEventListener("click", () => {
  refresh().catch((error) => toast(error.message));
});

els.brandFilters.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-brand]");
  if (!chip) return;
  state.brand = chip.dataset.brand;
  renderFilters();
  renderProducts();
});

els.categoryFilter.addEventListener("change", () => {
  state.category = els.categoryFilter.value;
  renderProducts();
});

els.customerSelect.addEventListener("change", () => {
  state.customerId = els.customerSelect.value;
  sessionStorage.setItem("stride-customer", state.customerId);
  renderCart();
});

els.orderFilter.addEventListener("change", () => {
  state.orderFilter = els.orderFilter.value;
  renderOrders();
});

document.querySelector("#product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.querySelector("#product-id").value;
  const payload = {
    brand: document.querySelector("#product-brand").value.trim(),
    name: document.querySelector("#product-name").value.trim(),
    category: document.querySelector("#product-category").value,
    size: document.querySelector("#product-size").value.trim(),
    color: document.querySelector("#product-color").value.trim(),
    description: document.querySelector("#product-description").value.trim(),
    price: Number(document.querySelector("#product-price").value),
    stock: Number(document.querySelector("#product-stock").value),
  };
  if (!Number.isInteger(payload.stock)) {
    toast("Stock must be a whole number");
    return;
  }
  try {
    await api(id ? `/api/products/${id}` : "/api/products", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetProductForm();
    toast(id ? "Shoe updated" : "Shoe added");
    await refresh();
  } catch (error) {
    toast(error.message);
  }
});

document.querySelector("#product-cancel").addEventListener("click", resetProductForm);

document.querySelector("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.querySelector("#user-id").value;
  const payload = {
    name: document.querySelector("#user-name").value.trim(),
    email: document.querySelector("#user-email").value.trim(),
  };
  try {
    await api(id ? `/api/users/${id}` : "/api/users", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetUserForm();
    toast(id ? "Customer updated" : "Customer added");
    await refresh();
  } catch (error) {
    toast(error.message);
  }
});

document.querySelector("#user-cancel").addEventListener("click", resetUserForm);

document.body.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const id = Number(button.dataset.id);
  const action = button.dataset.action;

  try {
    if (action === "add-cart") {
      const product = state.products.find((entry) => entry.id === id);
      const quantity = Number(document.querySelector(`#qty-${id}`).value);
      if (!product || !Number.isInteger(quantity) || quantity < 1) return;
      const existing = state.cart.find((item) => item.productId === id);
      const nextQty = (existing ? existing.quantity : 0) + quantity;
      if (nextQty > product.stock) {
        toast(`Only ${product.stock} in stock`);
        return;
      }
      if (existing) existing.quantity = nextQty;
      else {
        state.cart.push({
          productId: id,
          brand: product.brand,
          name: product.name,
          size: product.size,
          color: product.color,
          price: product.price,
          quantity,
        });
      }
      saveCart();
      renderCart();
      return;
    }

    if (action === "remove-cart") {
      state.cart = state.cart.filter((item) => item.productId !== id);
      saveCart();
      renderCart();
      return;
    }

    if (action === "edit-product") {
      const product = state.products.find((entry) => entry.id === id);
      if (!product) return;
      document.querySelector("#product-id").value = String(product.id);
      document.querySelector("#product-brand").value = product.brand;
      document.querySelector("#product-name").value = product.name;
      document.querySelector("#product-category").value = product.category;
      document.querySelector("#product-size").value = product.size;
      document.querySelector("#product-color").value = product.color;
      document.querySelector("#product-description").value = product.description;
      document.querySelector("#product-price").value = product.price;
      document.querySelector("#product-stock").value = product.stock;
      document.querySelector("#product-form-title").textContent = "Edit shoe";
      document.querySelector("#product-submit").textContent = "Save shoe";
      document.querySelector("#product-cancel").hidden = false;
      document.querySelector("#product-form").scrollIntoView({ behavior: "smooth" });
      return;
    }

    if (action === "delete-product") {
      const product = state.products.find((entry) => entry.id === id);
      if (!product || !confirm(`Delete ${shoeLabel(product)}?`)) return;
      await api(`/api/products/${id}`, { method: "DELETE" });
      if (document.querySelector("#product-id").value === String(id)) resetProductForm();
      toast("Shoe deleted");
      await refresh();
      return;
    }

    if (action === "edit-user") {
      const user = state.users.find((entry) => entry.id === id);
      if (!user) return;
      document.querySelector("#user-id").value = String(user.id);
      document.querySelector("#user-name").value = user.name;
      document.querySelector("#user-email").value = user.email;
      document.querySelector("#user-form-title").textContent = "Edit customer";
      document.querySelector("#user-submit").textContent = "Save customer";
      document.querySelector("#user-cancel").hidden = false;
      showView("customers");
      return;
    }

    if (action === "delete-user") {
      const user = state.users.find((entry) => entry.id === id);
      if (!user || !confirm(`Delete ${user.name}?`)) return;
      await api(`/api/users/${id}`, { method: "DELETE" });
      if (document.querySelector("#user-id").value === String(id)) resetUserForm();
      toast("Customer deleted");
      await refresh();
      return;
    }

    if (action === "cancel-order") {
      if (!confirm(`Cancel order #${id}? The shoes will return to stock.`)) return;
      await api(`/api/orders/${id}/cancel`, { method: "POST" });
      toast("Order cancelled");
      await refresh();
    }
  } catch (error) {
    toast(error.message);
  }
});

els.placeOrder.addEventListener("click", async () => {
  els.placeOrder.disabled = true;
  try {
    const order = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify({
        user_id: Number(state.customerId),
        items: state.cart.map((item) => ({ product_id: item.productId, quantity: item.quantity })),
      }),
    });
    state.cart = [];
    saveCart();
    toast(`Order #${order.id} placed`);
    await refresh();
    showView("orders");
  } catch (error) {
    toast(error.message);
    await refresh();
  }
});

refresh().catch((error) => toast(error.message));
