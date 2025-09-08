import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import platform
from typing import Optional
from dashboard import Dashboard
from inventory import InventoryManager
from transactions import TransactionManager
from sales_summary import SalesSummary

try:
    from PIL import Image
    pillow_available = True
except ImportError:
    pillow_available = False

class LoginApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shinano POS - Login")
        self.root.geometry("300x250")
        self.root.configure(bg="#F5F6F5")
        self.set_window_icon(self.root)
        self.db_path = self.get_writable_db_path()
        self.conn = None
        self.create_database()
        self.setup_gui()

    def set_window_icon(self, window: tk.Tk):
        """Set the window and taskbar icon for the given window."""
        try:
            # Determine the path to the icon files
            base_path = os.path.dirname(__file__)
            ico_path = os.path.join(base_path, "shinano.ico")
            png_path = os.path.join(base_path, "shinano.png")

            # Check if ICO file exists for Windows taskbar
            if platform.system() == "Windows":
                if os.path.exists(ico_path):
                    window.iconbitmap(ico_path)
                elif os.path.exists(png_path) and pillow_available:
                    # Convert PNG to ICO if Pillow is available
                    try:
                        img = Image.open(png_path)
                        img.save(ico_path, format="ICO")
                        window.iconbitmap(ico_path)
                    except Exception as e:
                        print(f"Error converting PNG to ICO: {e}")
                        messagebox.showwarning("Warning", "Failed to convert icon for taskbar", parent=window)
                else:
                    # Fallback to iconphoto for PNG
                    try:
                        icon = tk.PhotoImage(file=png_path)
                        window.iconphoto(True, icon)
                    except tk.TclError as e:
                        print(f"Error loading PNG icon: {e}")
                        messagebox.showwarning("Warning", "Failed to load application icon", parent=window)
            else:
                # For non-Windows platforms, use iconphoto with PNG
                if os.path.exists(png_path):
                    icon = tk.PhotoImage(file=png_path)
                    window.iconphoto(True, icon)
                else:
                    print("Icon file (shinano.png) not found")
                    messagebox.showwarning("Warning", "Application icon not found", parent=window)
        except tk.TclError as e:
            print(f"Error setting icon: {e}")
            messagebox.showwarning("Warning", "Failed to set application icon", parent=window)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory {db_dir}: {e}")
            messagebox.showerror("Error", f"Cannot create database directory: {e}", parent=self.root)
            raise
        db_path = os.path.join(db_dir, db_name)
        return db_path

    def create_database(self) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT,
                        role TEXT,
                        status TEXT DEFAULT 'Online'
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS inventory (
                        item_id TEXT PRIMARY KEY,
                        name TEXT,
                        type TEXT,
                        retail_price REAL DEFAULT 0.0,
                        unit_price REAL DEFAULT 0.0,
                        quantity INTEGER DEFAULT 0,
                        supplier TEXT
                    )
                ''')
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'retail_price' not in columns and 'price' in columns:
                    cursor.execute("ALTER TABLE inventory RENAME COLUMN price TO retail_price")
                    print("Renamed price to retail_price in inventory table.")
                if 'unit_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN unit_price REAL DEFAULT 0.0")
                    print("Added unit_price column to inventory table.")
                if 'supplier' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN supplier TEXT")
                    print("Added supplier column to inventory table.")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        transaction_id TEXT PRIMARY KEY,
                        items TEXT,
                        total_amount REAL DEFAULT 0.0,
                        cash_paid REAL DEFAULT 0.0,
                        change_amount REAL DEFAULT 0.0,
                        timestamp TEXT,
                        status TEXT,
                        payment_method TEXT,
                        customer_id TEXT
                    )
                ''')
                cursor.execute("PRAGMA table_info(transactions)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'payment_method' not in columns:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT")
                if 'customer_id' not in columns:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN customer_id TEXT")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS funds (
                        fund_id TEXT PRIMARY KEY,
                        type TEXT,
                        amount REAL DEFAULT 0.0,
                        timestamp TEXT,
                        user TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS customers (
                        customer_id TEXT PRIMARY KEY,
                        name TEXT,
                        contact TEXT,
                        address TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS likes (
                        like_id TEXT PRIMARY KEY,
                        transaction_id TEXT,
                        customer_id TEXT,
                        timestamp TEXT,
                        user TEXT,
                        FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
                        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transaction_log (
                        log_id TEXT PRIMARY KEY,
                        action TEXT,
                        details TEXT,
                        timestamp TEXT,
                        user TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_sales (
                        sale_date TEXT PRIMARY KEY,
                        total_sales REAL DEFAULT 0.0,
                        unit_sales INTEGER DEFAULT 0,
                        net_profit REAL DEFAULT 0.0,
                        user TEXT
                    )
                ''')
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("yamato", "ycb-0001", "Drug Lord", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("kongo", "kcb-0001", "User", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("manager", "mcb-0001", "Manager", "Online"))
                self.conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to set up database: {e}", parent=self.root)
            self.root.destroy()

    def scale_size(self, size: int, root: tk.Tk) -> int:
        base_resolution = 1920
        current_width = root.winfo_screenwidth()
        scaling_factor = current_width / base_resolution
        return int(size * scaling_factor)

    def setup_gui(self):
        main_frame = tk.Frame(self.root, bg="#F5F6F5")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Shinano POS Login", font=("Helvetica", self.scale_size(18, self.root), "bold"),
                 bg="#F5F6F5", fg="#2C3E50").pack(pady=self.scale_size(10, self.root))

        tk.Label(main_frame, text="Username:", font=("Helvetica", self.scale_size(14, self.root)),
                 bg="#F5F6F5", fg="#2C3E50").pack()
        self.username_entry = tk.Entry(main_frame, font=("Helvetica", self.scale_size(14, self.root)), bg="#F4E1C1")
        self.username_entry.pack(pady=self.scale_size(5, self.root))

        tk.Label(main_frame, text="Password:", font=("Helvetica", self.scale_size(14, self.root)),
                 bg="#F5F6F5", fg="#2C3E50").pack()
        self.password_entry = tk.Entry(main_frame, show="*", font=("Helvetica", self.scale_size(14, self.root)), bg="#F4E1C1")
        self.password_entry.pack(pady=self.scale_size(5, self.root))

        tk.Button(main_frame, text="Login", command=self.validate_login,
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, self.root), "bold"),
                  activebackground="#2C3E50", activeforeground="#F5F6F5",
                  padx=self.scale_size(12, self.root), pady=self.scale_size(6, self.root)).pack(pady=self.scale_size(10, self.root))

        self.password_entry.bind("<Return>", lambda e: self.validate_login())

    def validate_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password are required", parent=self.root)
            return

        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username, password, role FROM users WHERE username = ? AND password = ?",
                              (username, password))
                user = cursor.fetchone()
                if user:
                    username, _, role = user
                    self.redirect_to_module(username, role)
                else:
                    messagebox.showerror("Error", "Invalid username or password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Login failed: {e}", parent=self.root)

    def redirect_to_module(self, username: str, role: str):
        self.root.destroy()
        new_root = tk.Tk()
        self.set_window_icon(new_root)
        if role == "Drug Lord":
            self.show_account_management(new_root, username, role)
        elif role == "Manager":
            self.show_manager_dashboard(new_root, username, role)
        elif role == "User":
            Dashboard(new_root, current_user=username, user_role=role)
        else:
            messagebox.showerror("Error", "Unknown user role", parent=new_root)
            new_root.destroy()
        new_root.mainloop()

    def return_to_login(self, current_root: tk.Tk):
        current_root.destroy()
        new_root = tk.Tk()
        app = LoginApp(new_root)
        new_root.mainloop()

    def show_account_management(self, root: tk.Tk, username: str, role: str):
        root.title("Account Management")
        root.geometry("300x500")
        root.configure(bg="#F5F6F5")
        self.set_window_icon(root)
        tk.Label(root, text="Account Management - Drug Lord", font=("Helvetica", self.scale_size(18, root), "bold"),
                 bg="#F5F6F5", fg="#2C3E50").pack(pady=self.scale_size(20, root))
        tk.Button(root, text="Manage Users", command=lambda: self.manage_users(root, username, role),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))
        tk.Button(root, text="Logout", command=lambda: self.return_to_login(root),
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))

    def manage_users(self, root: tk.Tk, username: str, role: str):
        manage_window = tk.Toplevel(root)
        manage_window.title("Manage Users")
        manage_window.geometry("600x400")
        manage_window.configure(bg="#F5F6F5")
        self.set_window_icon(manage_window)

        tk.Label(manage_window, text="User Management", font=("Helvetica", self.scale_size(16, root), "bold"),
                 bg="#F5F6F5", fg="#2C3E50").pack(pady=self.scale_size(10, root))

        columns = ("Username", "Role", "Status")
        user_table = ttk.Treeview(manage_window, columns=columns, show="headings")
        for col in columns:
            user_table.heading(col, text=col)
            user_table.column(col, width=self.scale_size(150, root))
        user_table.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username, role, status FROM users")
                for user in cursor.fetchall():
                    user_table.insert("", "end", values=user)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to load users: {e}", parent=manage_window)

        button_frame = tk.Frame(manage_window, bg="#F5F6F5")
        button_frame.pack(pady=5)

        tk.Button(button_frame, text="Add User", command=lambda: self.add_user(manage_window, user_table, root),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Update User", command=lambda: self.update_user(manage_window, user_table, root),
                  bg="#F1C40F", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Delete User", command=lambda: self.delete_user(manage_window, user_table, username, root),
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Close", command=manage_window.destroy,
                  bg="#95A5A6", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)

    def add_user(self, parent: tk.Tk, user_table: ttk.Treeview, root: tk.Tk):
        add_window = tk.Toplevel(parent)
        add_window.title("Add User")
        add_window.geometry("400x300")
        add_window.configure(bg="#F5F6F5")
        self.set_window_icon(add_window)

        tk.Label(add_window, text="Username:", font=("Helvetica", self.scale_size(14, root)), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)
        username_entry = tk.Entry(add_window, font=("Helvetica", self.scale_size(14, root)))
        username_entry.pack(pady=5)

        tk.Label(add_window, text="Password:", font=("Helvetica", self.scale_size(14, root)), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)
        password_entry = tk.Entry(add_window, show="*", font=("Helvetica", self.scale_size(14, root)))
        password_entry.pack(pady=5)

        tk.Label(add_window, text="Role:", font=("Helvetica", self.scale_size(14, root)), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)
        role_var = tk.StringVar(value="User")
        ttk.Combobox(add_window, textvariable=role_var, values=["User", "Manager", "Drug Lord"],
                     state="readonly", font=("Helvetica", self.scale_size(14, root))).pack(pady=5)

        def save_user():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            role = role_var.get()
            if not username or not password:
                messagebox.showerror("Error", "Username and password are required", parent=add_window)
                return
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)",
                                  (username, password, role, "Online"))
                    self.conn.commit()
                    user_table.insert("", "end", values=(username, role, "Online"))
                    messagebox.showinfo("Success", "User added successfully", parent=add_window)
                    add_window.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Username already exists", parent=add_window)
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to add user: {e}", parent=add_window)

        tk.Button(add_window, text="Save", command=save_user,
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=10)
        tk.Button(add_window, text="Cancel", command=add_window.destroy,
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=5)

    def update_user(self, parent: tk.Tk, user_table: ttk.Treeview, root: tk.Tk):
        selected_item = user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "Please select a user to update", parent=parent)
            return

        username = user_table.item(selected_item)["values"][0]
        update_window = tk.Toplevel(parent)
        update_window.title("Update User")
        update_window.geometry("400x300")
        update_window.configure(bg="#F5F6F5")
        self.set_window_icon(update_window)

        tk.Label(update_window, text=f"Updating User: {username}", font=("Helvetica", self.scale_size(14, root), "bold"),
                 bg="#F5F6F5", fg="#2C3E50").pack(pady=5)

        tk.Label(update_window, text="New Password:", font=("Helvetica", self.scale_size(14, root)), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)
        password_entry = tk.Entry(update_window, show="*", font=("Helvetica", self.scale_size(14, root)))
        password_entry.pack(pady=5)

        tk.Label(update_window, text="Role:", font=("Helvetica", self.scale_size(14, root)), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)
        role_var = tk.StringVar(value=user_table.item(selected_item)["values"][1])
        ttk.Combobox(update_window, textvariable=role_var, values=["User", "Manager", "Drug Lord"],
                     state="readonly", font=("Helvetica", self.scale_size(14, root))).pack(pady=5)

        def save_update():
            new_password = password_entry.get().strip()
            new_role = role_var.get()
            if not new_password:
                messagebox.showerror("Error", "Password is required", parent=update_window)
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("UPDATE users SET password = ?, role = ? WHERE username = ?",
                                  (new_password, new_role, username))
                    self.conn.commit()
                    user_table.item(selected_item, values=(username, new_role, "Online"))
                    messagebox.showinfo("Success", "User updated successfully", parent=update_window)
                    update_window.destroy()
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to update user: {e}", parent=update_window)

        tk.Button(update_window, text="Save", command=save_update,
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=10)
        tk.Button(update_window, text="Cancel", command=update_window.destroy,
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=5)

    def delete_user(self, parent: tk.Tk, user_table: ttk.Treeview, current_username: str, root: tk.Tk):
        selected_item = user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "Please select a user to delete", parent=parent)
            return

        username = user_table.item(selected_item)["values"][0]
        if username == current_username:
            messagebox.showerror("Error", "Cannot delete the currently logged-in user", parent=parent)
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete user '{username}'?", parent=parent):
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                    self.conn.commit()
                    user_table.delete(selected_item)
                    messagebox.showinfo("Success", "User deleted successfully", parent=parent)
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to delete user: {e}", parent=parent)

    def show_manager_dashboard(self, root: tk.Tk, username: str, role: str):
        root.title("Manager Dashboard")
        root.geometry("300x300")
        root.configure(bg="#F5F6F5")
        self.set_window_icon(root)

        main_frame = tk.Frame(root, bg="#F5F6F5")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(main_frame, text="Manager Dashboard", font=("Helvetica", self.scale_size(18, root), "bold"),
                 bg="#F5F6F5", fg="#2C3E50").pack(pady=self.scale_size(20, root))

        tk.Button(main_frame, text="Inventory Management",
                  command=lambda: self.open_module(root, InventoryManager, username, role),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))
        tk.Button(main_frame, text="Transaction Management",
                  command=lambda: self.open_module(root, TransactionManager, username, role),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))
        tk.Button(main_frame, text="Sales Summary",
                  command=lambda: self.open_module(root, SalesSummary, username, role, db_path=self.db_path),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))
        tk.Button(main_frame, text="Logout", command=lambda: self.return_to_login(root),
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=self.scale_size(10, root))

    def open_module(self, current_root: tk.Tk, module_class, username: str, role: str, db_path: Optional[str] = None):
        new_window = tk.Toplevel(current_root)
        self.set_window_icon(new_window)
        if module_class == SalesSummary:
            module_class(new_window, current_user=username, user_role=role, db_path=db_path)
        else:
            module_class(new_window, current_user=username, user_role=role)

    def __del__(self):
        if self.conn:
            self.conn.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()

