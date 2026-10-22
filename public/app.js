const clinicPhone = "919876543210";
const servicesState = [];

const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const qs = (selector) => document.querySelector(selector);

function setWhatsAppLinks() {
  const message = encodeURIComponent("Hi CareNest Clinic, I would like to book an appointment.");
  const url = `https://wa.me/${clinicPhone}?text=${message}`;
  qs("#whatsappTop").href = url;
  qs("#whatsappLead").href = url;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function renderServices(services) {
  const icons = ["+", "✓", "D", "P", "W", "T"];
  qs("#serviceGrid").innerHTML = services
    .map(
      (service, index) => `
        <article class="service-card">
          <span class="icon">${icons[index] || "+"}</span>
          <h3>${service.name}</h3>
          <p>${service.description}</p>
          <span class="meta">${service.duration} · ${currency.format(service.price)}</span>
        </article>
      `
    )
    .join("");

  qs("#pricingList").innerHTML = services
    .map(
      (service) => `
        <div class="price-row">
          <div>
            <strong>${service.name}</strong>
            <small>${service.duration}</small>
          </div>
          <span class="price">${currency.format(service.price)}</span>
        </div>
      `
    )
    .join("");

  const options = services
    .map((service) => `<option value="${service.name}">${service.name}</option>`)
    .join("");
  qs("#serviceSelect").innerHTML = `<option value="">Select service</option>${options}`;
  qs("#leadInterest").innerHTML = `<option value="">Select interest</option>${options}`;
}

function setMinimumDate() {
  const dateInput = qs('input[name="appointment_date"]');
  dateInput.min = new Date().toISOString().slice(0, 10);
}

async function loadServices() {
  const { services } = await api("/api/services");
  servicesState.splice(0, servicesState.length, ...services);
  renderServices(services);
}

function serializeForm(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function handleBooking(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = qs("#bookingStatus");
  status.textContent = "Saving booking...";
  try {
    const payload = serializeForm(form);
    const result = await api("/api/appointments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    status.textContent = `Booked successfully. Reference #${result.id}.`;
    form.reset();
    setMinimumDate();
    await loadAdmin();
  } catch (error) {
    status.textContent = error.message;
  }
}

async function handleLead(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = qs("#leadStatus");
  status.textContent = "Saving callback request...";
  try {
    const result = await api("/api/leads", {
      method: "POST",
      body: JSON.stringify(serializeForm(form)),
    });
    status.textContent = `Callback request saved. Lead #${result.id}.`;
    form.reset();
    await loadAdmin();
  } catch (error) {
    status.textContent = error.message;
  }
}

function renderStats(summary) {
  const labels = [
    ["Appointments", summary.appointments],
    ["New requests", summary.newAppointments],
    ["Today", summary.todayAppointments],
    ["Leads", summary.leads],
  ];
  qs("#adminStats").innerHTML = labels
    .map(
      ([label, value]) => `
        <div class="stat-card">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `
    )
    .join("");
}

function renderAppointments(appointments) {
  const rows = appointments.map((appointment) => {
    const slot = `${appointment.appointment_date} at ${appointment.appointment_time}`;
    return `
      <tr>
        <td>
          <strong>${appointment.name}</strong>
          <small>${appointment.phone}${appointment.email ? ` · ${appointment.email}` : ""}</small>
        </td>
        <td>
          ${appointment.service}
          <small>${appointment.notes || "No notes"}</small>
        </td>
        <td>${slot}</td>
        <td>
          <select class="status-select" data-id="${appointment.id}">
            ${["New", "Confirmed", "Completed", "Cancelled"]
              .map(
                (status) =>
                  `<option value="${status}" ${status === appointment.status ? "selected" : ""}>${status}</option>`
              )
              .join("")}
          </select>
        </td>
      </tr>
    `;
  });
  qs("#appointmentRows").innerHTML =
    rows.join("") || `<tr><td colspan="4">No appointments yet.</td></tr>`;
}

function renderLeads(leads) {
  qs("#leadRows").innerHTML =
    leads
      .map(
        (lead) => `
          <article class="lead-item">
            <strong>${lead.name}</strong>
            <small>${lead.phone} · ${lead.interest}</small>
            <small>${lead.message || "No message"}</small>
          </article>
        `
      )
      .join("") || `<p class="form-status">No leads yet.</p>`;
}

async function loadAdmin() {
  const [summary, appointments, leads] = await Promise.all([
    api("/api/admin/summary"),
    api("/api/admin/appointments"),
    api("/api/admin/leads"),
  ]);
  renderStats(summary);
  renderAppointments(appointments.appointments);
  renderLeads(leads.leads);
}

async function updateStatus(event) {
  const target = event.target;
  if (!target.matches(".status-select")) {
    return;
  }
  await api(`/api/appointments/${target.dataset.id}/status`, {
    method: "POST",
    body: JSON.stringify({ status: target.value }),
  });
  await loadAdmin();
}

async function boot() {
  setWhatsAppLinks();
  setMinimumDate();
  await loadServices();
  await loadAdmin();
  qs("#bookingForm").addEventListener("submit", handleBooking);
  qs("#leadForm").addEventListener("submit", handleLead);
  qs("#refreshAdmin").addEventListener("click", loadAdmin);
  qs("#appointmentRows").addEventListener("change", updateStatus);
}

boot().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div style="padding: 12px; background: #fee2e2; color: #7f1d1d;">${error.message}</div>`
  );
});
