const { createApp } = Vue;

createApp({
  data() {
    return {
      user: JSON.parse(localStorage.getItem("user") || "null"),
      tab: "income",
      auth: {
        phone: "",
        pin: "",
        pinConfirm: "",
        step: "check",
      },
      dashboard: {
        period: { season_label: "", start_date: "", end_date: "" },
        totals: { income_total: 0, expense_total: 0, difference: 0 },
      },
      availablePeriods: [],
      selectedSeason: "",
      config: {
        expense_categories: [],
      },
      memberStatuses: [],
      members: [],
      history: { incomes: [], expenses: [] },
      auditLogs: [],
      forms: {
        otherIncome: { amount: "", entry_date: new Date().toISOString().slice(0, 10), description: "" },
        memberPayment: { member_id: "", amount: "", entry_date: new Date().toISOString().slice(0, 10) },
        expense: { category: "", amount: "", entry_date: new Date().toISOString().slice(0, 10), description: "" },
        member: {
          first_name: "",
          last_name: "",
          phone: "",
          status: "Member",
          membership_fee: 0,
          joining_fee_paid: false,
          role: "member",
        },
        period: { season_label: "", default_membership_fee: 0, carry_over: 0 },
      },
      selectedFile: null,
      successMessage: "",
      errorMessage: "",
      historyFilter: { month: "", incomeType: "", expenseCategory: "" },
      historyCollapsed: { incomes: false, expenses: false },
      editIncome: { id: null, amount: "", entry_date: "", description: "" },
      editExpense: { id: null, category: "", amount: "", entry_date: "", description: "" },
    };
  },
  computed: {
    canWriteIncome() {
      return ["cashier", "admin"].includes(this.user?.role);
    },
    canWriteExpense() {
      return ["cashier", "admin"].includes(this.user?.role);
    },
    canManageMembers() {
      return ["board", "admin"].includes(this.user?.role);
    },
    canManagePeriod() {
      return ["board", "admin"].includes(this.user?.role);
    },
    canEditEntries() {
      return this.user?.role === "admin";
    },
    canViewAuditLogs() {
      return this.user?.role === "admin";
    },
    roleOptions() {
      return [
        { value: "member", label: "Member" },
        { value: "cashier", label: "Cashier" },
        { value: "board", label: "Board" },
        { value: "auditor", label: "Auditor" },
        { value: "admin", label: "Administrator" },
      ];
    },
    statusOptions() {
      const options = [...this.memberStatuses];
      const seen = new Set(options);
      this.members.forEach((m) => {
        const value = (m.status || "").trim();
        if (value && !seen.has(value)) {
          options.push(value);
          seen.add(value);
        }
      });
      return options;
    },
    historyMonths() {
      const months = new Set();
      [...(this.history.incomes || []), ...(this.history.expenses || [])].forEach((r) => {
        if (r.entry_date) months.add(r.entry_date.slice(0, 7));
      });
      return [...months].sort().reverse();
    },
    historyIncomeTypes() {
      const types = new Set();
      (this.history.incomes || []).forEach((r) => {
        if (r.type) types.add(r.type);
      });
      return [...types].sort();
    },
    historyExpenseCategories() {
      const cats = new Set();
      (this.history.expenses || []).forEach((r) => {
        if (r.category) cats.add(r.category);
      });
      return [...cats].sort();
    },
    filteredIncomes() {
      return (this.history.incomes || []).filter((r) => {
        if (this.historyFilter.month && !r.entry_date.startsWith(this.historyFilter.month)) return false;
        if (this.historyFilter.incomeType && r.type !== this.historyFilter.incomeType) return false;
        return true;
      });
    },
    filteredExpenses() {
      return (this.history.expenses || []).filter((r) => {
        if (this.historyFilter.month && !r.entry_date.startsWith(this.historyFilter.month)) return false;
        if (this.historyFilter.expenseCategory && r.category !== this.historyFilter.expenseCategory) return false;
        return true;
      });
    },
  },
  methods: {
    resetMessages() {
      this.successMessage = "";
      this.errorMessage = "";
    },
    isAmountMissing(value) {
      return value === null || value === undefined || String(value).trim() === "";
    },
    isMemberFullyPaid(member) {
      const fee = Number(member?.membership_fee || 0);
      const paid = Number(member?.paid_this_period || 0);
      if (!Number.isFinite(fee) || !Number.isFinite(paid)) {
        return false;
      }
      if (fee <= 0) {
        return true;
      }
      return paid >= fee;
    },
    async api(path, options = {}) {
      const headers = options.headers || {};
      const response = await fetch(path, { ...options, headers, credentials: options.credentials || "same-origin" });
      const contentType = response.headers.get("content-type") || "";
      let data = null;
      let rawText = "";
      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        rawText = await response.text();
      }
      if (!response.ok) {
        if (response.status === 401) {
          this.user = null;
          localStorage.removeItem("user");
          this.auth.step = "check";
        }
        const fallbackMessage = rawText
          ? `HTTP ${response.status}: ${rawText.slice(0, 200)}`
          : `HTTP ${response.status}`;
        const error = new Error(data?.error || fallbackMessage || "Request failed");
        error.status = response.status;
        throw error;
      }
      return data;
    },
    async loadConfig() {
      this.config = await this.api("/api/config");
    },
    async loadMemberStatuses() {
      if (!this.user || !this.canManageMembers) {
        this.memberStatuses = [];
        return;
      }
      const data = await this.api("/api/member-statuses");
      this.memberStatuses = data.statuses || [];
      if (this.memberStatuses.length > 0 && !this.memberStatuses.includes(this.forms.member.status)) {
        this.forms.member.status = this.memberStatuses[0];
      }
    },
    async checkPhone() {
      this.resetMessages();
      try {
        const data = await this.api("/api/auth/init", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: this.auth.phone }),
        });
        this.auth.step = data.needs_pin_setup ? "setup" : "login";
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async setupPin() {
      this.resetMessages();
      try {
        await this.api("/api/auth/setup-pin", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            phone: this.auth.phone,
            pin: this.auth.pin,
            pin_confirm: this.auth.pinConfirm,
          }),
        });
        this.successMessage = "PIN saved. Please sign in.";
        this.auth.step = "login";
        this.auth.pin = "";
        this.auth.pinConfirm = "";
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async login() {
      this.resetMessages();
      try {
        const data = await this.api("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: this.auth.phone, pin: this.auth.pin }),
        });
        this.user = data.user;
        localStorage.setItem("user", JSON.stringify(this.user));
        await this.refreshAll();
        this.tab = "member-list";
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async logout() {
      try {
        await this.api("/api/auth/logout", { method: "POST" });
      } catch (_err) {
        void _err;
      }
      this.user = null;
      localStorage.removeItem("user");
      this.auth = { phone: "", pin: "", pinConfirm: "", step: "check" };
      this.successMessage = "";
      this.errorMessage = "";
    },
    async loadDashboard() {
      const seasonQuery = this.selectedSeason ? `?season_label=${encodeURIComponent(this.selectedSeason)}` : "";
      this.dashboard = await this.api(`/api/dashboard${seasonQuery}`);
      this.forms.period.season_label = this.dashboard.period.season_label;
      this.forms.period.carry_over = this.dashboard.period.carry_over;
      if (!this.selectedSeason) {
        this.selectedSeason = this.dashboard.period.season_label;
      }
    },
    async loadAvailablePeriods() {
      const data = await this.api("/api/periods/available");
      this.availablePeriods = data.periods || [];
      if (!this.selectedSeason && this.availablePeriods.length > 0) {
        const activePeriod = this.availablePeriods.find((p) => p.active);
        this.selectedSeason = (activePeriod || this.availablePeriods[0]).season_label;
      }
    },
    async loadMembers() {
      if (!this.user) return;
      const seasonQuery = this.selectedSeason ? `?season_label=${encodeURIComponent(this.selectedSeason)}` : "";
      this.members = await this.api(`/api/members${seasonQuery}`);
    },
    async loadHistory() {
      if (!["cashier", "board", "admin", "auditor"].includes(this.user?.role)) return;
      const seasonQuery = this.selectedSeason ? `?season_label=${encodeURIComponent(this.selectedSeason)}` : "";
      this.history = await this.api(`/api/history${seasonQuery}`);
    },
    async loadAuditLogs() {
      if (!this.canViewAuditLogs) {
        this.auditLogs = [];
        return;
      }
      const seasonQuery = this.selectedSeason ? `?season_label=${encodeURIComponent(this.selectedSeason)}` : "";
      const data = await this.api(`/api/audit-logs${seasonQuery}`);
      this.auditLogs = data.audit_logs || [];
    },
    async onSeasonChange() {
      if (!this.user) return;
      await this.loadDashboard();
      await this.loadMembers();
      await this.loadHistory();
      await this.loadAuditLogs();
    },
    async refreshAll() {
      await this.loadConfig();
      if (this.user) {
        await this.loadMemberStatuses();
        await this.loadAvailablePeriods();
        await this.loadDashboard();
        await this.loadMembers();
        await this.loadHistory();
        await this.loadAuditLogs();
      }
    },
    async addOtherIncome() {
      this.resetMessages();
      if (this.isAmountMissing(this.forms.otherIncome.amount)) {
        this.errorMessage = "Please enter an amount.";
        return;
      }
      try {
        await this.api("/api/incomes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.forms.otherIncome),
        });
        this.successMessage = "Income added";
        this.forms.otherIncome.amount = "";
        this.forms.otherIncome.description = "";
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async addMemberPayment() {
      this.resetMessages();
      if (this.isAmountMissing(this.forms.memberPayment.amount)) {
        this.errorMessage = "Please enter an amount.";
        return;
      }
      try {
        const memberId = this.forms.memberPayment.member_id;
        await this.api(`/api/members/${memberId}/payment`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: this.forms.memberPayment.amount,
            entry_date: this.forms.memberPayment.entry_date,
          }),
        });
        this.successMessage = "Member payment added";
        this.forms.memberPayment.amount = "";
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    onFileChange(event) {
      this.selectedFile = event.target.files[0] || null;
    },
    async addExpense() {
      this.resetMessages();
      if (this.isAmountMissing(this.forms.expense.amount)) {
        this.errorMessage = "Please enter an amount.";
        return;
      }
      try {
        const fd = new FormData();
        Object.entries(this.forms.expense).forEach(([k, v]) => fd.append(k, v));
        if (this.selectedFile) {
          fd.append("attachment", this.selectedFile);
        }
        await this.api("/api/expenses", { method: "POST", body: fd });
        this.successMessage = "Expense added";
        this.forms.expense.amount = "";
        this.forms.expense.description = "";
        this.selectedFile = null;
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    attachmentUrl(filename) {
      return `/api/attachments/${filename}`;
    },
    async openAttachment(filename) {
      this.resetMessages();
      let previewWindow = null;

      try {
        previewWindow = window.open("", "_blank");

        const response = await fetch(this.attachmentUrl(filename), {
          credentials: "same-origin",
        });

        if (!response.ok) {
          let message = "Failed to open attachment";
          try {
            const data = await response.json();
            message = data.error || message;
          } catch (_parseErr) {
            void _parseErr;
          }
          throw new Error(message);
        }

        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);

        if (previewWindow) {
          previewWindow.location.href = blobUrl;
        } else {
          window.open(blobUrl, "_blank");
        }

        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      } catch (err) {
        if (previewWindow) {
          previewWindow.close();
        }
        this.errorMessage = err.message;
      }
    },
    async addMember() {
      this.resetMessages();
      try {
        const payload = { ...this.forms.member, season_label: this.selectedSeason || this.forms.period.season_label };
        if (this.user.role !== "admin") {
          delete payload.role;
        }
        await this.api("/api/members", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        this.successMessage = "Member added";
        this.forms.member = {
          first_name: "",
          last_name: "",
          phone: "",
          status: this.memberStatuses[0] || "Member",
          membership_fee: 0,
          joining_fee_paid: false,
          role: "member",
        };
        await this.loadMembers();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async saveMember(member) {
      this.resetMessages();
      try {
        const payload = { ...member, season_label: this.selectedSeason || this.forms.period.season_label };
        await this.api(`/api/members/${member.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        this.successMessage = "Member details saved";
        await this.loadMembers();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async removeMember(memberId) {
      this.resetMessages();
      try {
        await this.api(`/api/members/${memberId}`, { method: "DELETE" });
        this.successMessage = "Member deleted";
        await this.loadMembers();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async clearMemberPin(memberId) {
      this.resetMessages();
      try {
        await this.api(`/api/members/${memberId}/pin`, { method: "DELETE" });
        this.successMessage = "PIN deleted";
        await this.loadMembers();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async setPeriod() {
      this.resetMessages();
      try {
        await this.api("/api/period", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            season_label: this.forms.period.season_label,
            default_membership_fee: this.forms.period.default_membership_fee,
            carry_over: this.forms.period.carry_over,
          }),
        });
        this.successMessage = "Reporting period saved";
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async exportBalance() {
      this.resetMessages();
      try {
        const seasonQuery = this.selectedSeason ? `?season_label=${encodeURIComponent(this.selectedSeason)}` : "";
        const res = await fetch(`/api/export${seasonQuery}`, {
          credentials: "same-origin",
        });
        if (!res.ok) {
          let message = "Export failed";
          try {
            const data = await res.json();
            message = data.error || message;
          } catch (_parseErr) {
            void _parseErr;
          }
          throw new Error(message);
        }
        const blob = await res.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "balance.xlsx";
        document.body.appendChild(link);
        link.click();
        link.remove();
        this.successMessage = "Balance exported successfully";
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    startIncomeEdit(row) {
      if (!this.canEditEntries) return;
      this.editIncome = {
        id: row.id,
        amount: row.amount,
        entry_date: row.entry_date,
        description: row.description || "",
      };
    },
    cancelIncomeEdit() {
      this.editIncome = { id: null, amount: "", entry_date: "", description: "" };
    },
    async saveIncomeEdit() {
      if (!this.editIncome.id) return;
      this.resetMessages();
      if (this.isAmountMissing(this.editIncome.amount)) {
        this.errorMessage = "Please enter an amount.";
        return;
      }
      try {
        await this.api(`/api/incomes/${this.editIncome.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: this.editIncome.amount,
            entry_date: this.editIncome.entry_date,
            description: this.editIncome.description,
          }),
        });
        this.successMessage = "Income record updated";
        this.cancelIncomeEdit();
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async removeIncome(row) {
      if (!this.canEditEntries) return;
      const ok = window.confirm("Are you sure you want to delete this income record?");
      if (!ok) return;
      this.resetMessages();
      try {
        await this.api(`/api/incomes/${row.id}`, { method: "DELETE" });
        this.successMessage = "Income record deleted";
        if (this.editIncome.id === row.id) {
          this.cancelIncomeEdit();
        }
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    startExpenseEdit(row) {
      if (!this.canEditEntries) return;
      this.editExpense = {
        id: row.id,
        category: row.category,
        amount: row.amount,
        entry_date: row.entry_date,
        description: row.description || "",
      };
    },
    cancelExpenseEdit() {
      this.editExpense = { id: null, category: "", amount: "", entry_date: "", description: "" };
    },
    async saveExpenseEdit() {
      if (!this.editExpense.id) return;
      this.resetMessages();
      if (this.isAmountMissing(this.editExpense.amount)) {
        this.errorMessage = "Please enter an amount.";
        return;
      }
      try {
        await this.api(`/api/expenses/${this.editExpense.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category: this.editExpense.category,
            amount: this.editExpense.amount,
            entry_date: this.editExpense.entry_date,
            description: this.editExpense.description,
          }),
        });
        this.successMessage = "Expense record updated";
        this.cancelExpenseEdit();
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
    async removeExpense(row) {
      if (!this.canEditEntries) return;
      const ok = window.confirm("Are you sure you want to delete this expense record?");
      if (!ok) return;
      this.resetMessages();
      try {
        await this.api(`/api/expenses/${row.id}`, { method: "DELETE" });
        this.successMessage = "Expense record deleted";
        if (this.editExpense.id === row.id) {
          this.cancelExpenseEdit();
        }
        await this.refreshAll();
      } catch (err) {
        this.errorMessage = err.message;
      }
    },
  },
  async mounted() {
    await this.loadConfig();
    if (this.user) {
      try {
        await this.refreshAll();
        this.tab = "member-list";
      } catch (_err) {
        void _err;
      }
    }
  },
}).mount("#app");
