import tkinter as tk
from tkinter import messagebox
from inventory import InventoryManager
from transactions import TransactionManager
from sales_summary import SalesSummary


class ManagerDashboard:
    def __init__(self, root: tk.Tk, username: str, role: str, db_path: str):
        self.root = root
        self.username = username
        self.role = role
        self.db_path = db_path

        self.setup_ui()
        self.root.bind("<F12>", self.open_login_window)

    def setup_ui(self):
        self.root.title("Manager Dashboard")
        win_w, win_h = 900, 600
        scr_w, scr_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.configure(bg="#ECF0F1")

        # --- Header ---
        header = tk.Frame(self.root, bg="#2C3E50", height=60)
        header.pack(fill="x", side="top")
        tk.Label(
            header,
            text=f"Manager Dashboard - {self.username}",
            font=("Helvetica", 20, "bold"),
            bg="#2C3E50",
            fg="white",
        ).pack(side="left", padx=20, pady=15)

        # --- Content area ---
        content = tk.Frame(self.root, bg="#ECF0F1")
        content.pack(fill="both", expand=True, padx=30, pady=30)

        # --- Card creator ---
        def create_card(parent, text, command, bg_color="#4DA8DA"):
            card = tk.Frame(parent, bg="white", relief="raised", bd=2)
            btn = tk.Button(
                card,
                text=text,
                command=command,
                bg=bg_color,
                fg="white",
                font=("Helvetica", 18, "bold"),
                relief="flat",
                cursor="hand2",
                wraplength=200,
            )
            btn.pack(expand=True, fill="both", padx=20, pady=20)
            return card

        # --- Grid layout (using pack for each row instead of mix) ---
        row1 = tk.Frame(content, bg="#ECF0F1")
        row1.pack(fill="x", expand=True)
        row2 = tk.Frame(content, bg="#ECF0F1")
        row2.pack(fill="x", expand=True)

        inv = create_card(row1, "📦 Inventory", lambda: self.open_module(InventoryManager))
        txn = create_card(row1, "💳 Transactions", lambda: self.open_module(TransactionManager))
        sales = create_card(row2, "📊 Sales Summary", lambda: self.open_module(SalesSummary))
        logout = create_card(row2, "🚪 Logout", self.logout, "#E74C3C")

        # --- Pack cards horizontally in each row ---
        inv.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        txn.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        sales.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        logout.pack(side="left", expand=True, fill="both", padx=20, pady=20)



    def open_login_window(self, event=None):
        """Close the dashboard and return to the main login screen."""
        from login import main  # Import the main login entry point
        self.root.destroy()     # ✅ Close current dashboard window
        main()                  # ✅ Open login window again


    def open_module(self, module_class):
        """Open a new window for the selected module with proper database access."""
        new = tk.Toplevel(self.root)
        try:
            # Pass db_path to all modules to ensure consistent database connection
            module_class(new, current_user=self.username, user_role=self.role, db_path=self.db_path)
        except TypeError:
            # In case a module does not require db_path (for compatibility)
            module_class(new, current_user=self.username, user_role=self.role)


    def logout(self):
        self.root.destroy()
        from login import main
        main()
