import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
from datetime import datetime


class AccountDashboard:
    def __init__(self, root: tk.Tk, username: str, role: str, db_path: str):
        self.root = root
        self.username = username
        self.role = role
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)

        self.setup_ui()

    # ------------------ UI SETUP ------------------
    def setup_ui(self):
        self.root.title("Admin Dashboard")
        win_w, win_h = 950, 600
        scr_w, scr_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.configure(bg="#ECF0F1")

        # --- Header ---
        header = tk.Frame(self.root, bg="#8E44AD", height=60)
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"Admin Dashboard - {self.username}",
            font=("Helvetica", 20, "bold"),
            bg="#8E44AD",
            fg="white",
        ).pack(side="left", padx=20, pady=15)

        # --- Content Area ---
        content = tk.Frame(self.root, bg="#ECF0F1")
        content.pack(fill="both", expand=True, padx=30, pady=30)

        row1 = tk.Frame(content, bg="#ECF0F1")
        row1.pack(fill="x", expand=True)
        row2 = tk.Frame(content, bg="#ECF0F1")
        row2.pack(fill="x", expand=True)

        def create_card(parent, text, command, color="#4DA8DA"):
            frame = tk.Frame(parent, bg="white", relief="raised", bd=2)
            btn = tk.Button(
                frame,
                text=text,
                command=command,
                bg=color,
                fg="white",
                font=("Helvetica", 18, "bold"),
                relief="flat",
                cursor="hand2",
                wraplength=200,
            )
            btn.pack(expand=True, fill="both", padx=20, pady=20)
            return frame

        manage_users = create_card(row1, "👥 Manage Users", self.manage_users, "#3498DB")
        backup_db = create_card(row1, "💾 Backup Database", self.backup_database, "#27AE60")
        compact_db = create_card(row2, "🧩 Compact Database", self.compact_database, "#F39C12")
        logout = create_card(row2, "🚪 Logout", self.logout, "#E74C3C")

        manage_users.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        backup_db.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        compact_db.pack(side="left", expand=True, fill="both", padx=20, pady=20)
        logout.pack(side="left", expand=True, fill="both", padx=20, pady=20)

    # ------------------ MANAGE USERS ------------------
    def manage_users(self):
        win = tk.Toplevel(self.root)
        win.title("Manage Users")
        win.geometry("900x550")
        win.configure(bg="#F5F6F5")

        tk.Label(
            win, text="User Management", font=("Helvetica", 22, "bold"), bg="#F5F6F5", fg="#2C3E50"
        ).pack(pady=10)

        columns = ("Username", "Role", "Status")
        table = ttk.Treeview(win, columns=columns, show="headings")
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=200, anchor="center")
        table.pack(fill="both", expand=True, padx=10, pady=10)

        self.refresh_user_table(table)

        btn_frame = tk.Frame(win, bg="#F5F6F5")
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Add User", command=lambda: self.add_user(win, table),
                  bg="#4DA8DA", fg="white", font=("Helvetica", 14, "bold"), relief="flat",
                  padx=20, pady=8).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Update User", command=lambda: self.update_user(win, table),
                  bg="#F1C40F", fg="white", font=("Helvetica", 14, "bold"), relief="flat",
                  padx=20, pady=8).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Delete User", command=lambda: self.delete_user(win, table),
                  bg="#E74C3C", fg="white", font=("Helvetica", 14, "bold"), relief="flat",
                  padx=20, pady=8).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Close", command=win.destroy,
                  bg="#95A5A6", fg="white", font=("Helvetica", 14, "bold"), relief="flat",
                  padx=20, pady=8).pack(side="left", padx=10)

    def refresh_user_table(self, table: ttk.Treeview):
        for item in table.get_children():
            table.delete(item)
        cur = self.conn.cursor()
        cur.execute("SELECT username, role, status FROM users")
        for row in cur.fetchall():
            table.insert("", "end", values=row)

    # ------------------ ADD USER ------------------
    def add_user(self, parent, table):
        win = tk.Toplevel(parent)
        win.title("Add User")
        win.geometry("400x350")
        win.configure(bg="#F5F6F5")

        tk.Label(win, text="Add New User", font=("Helvetica", 18, "bold"), bg="#F5F6F5").pack(pady=10)

        tk.Label(win, text="Username:", bg="#F5F6F5", font=("Helvetica", 14)).pack()
        username_entry = tk.Entry(win, font=("Helvetica", 14))
        username_entry.pack(pady=5)

        tk.Label(win, text="Password:", bg="#F5F6F5", font=("Helvetica", 14)).pack()
        password_entry = tk.Entry(win, font=("Helvetica", 14), show="*")
        password_entry.pack(pady=5)

        tk.Label(win, text="Role:", bg="#F5F6F5", font=("Helvetica", 14)).pack()
        role_box = ttk.Combobox(win, values=["User", "Manager", "Drug Lord"], state="readonly", font=("Helvetica", 13))
        role_box.current(0)
        role_box.pack(pady=5)

        def save_user():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            role = role_box.get()
            if not username or not password:
                messagebox.showerror("Error", "Username and password are required", parent=win)
                return
            try:
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)",
                    (username, password, role, "Online"),
                )
                self.conn.commit()
                messagebox.showinfo("Success", "User added successfully", parent=win)
                win.destroy()
                self.refresh_user_table(table)
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Username already exists", parent=win)

        tk.Button(win, text="Save", command=save_user, bg="#4DA8DA", fg="white",
                  font=("Helvetica", 14, "bold"), relief="flat", padx=20, pady=8).pack(pady=10)
        tk.Button(win, text="Cancel", command=win.destroy, bg="#E74C3C", fg="white",
                  font=("Helvetica", 14, "bold"), relief="flat", padx=20, pady=8).pack()

    # ------------------ UPDATE USER ------------------
    def update_user(self, parent, table):
        selected = table.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a user to update", parent=parent)
            return

        username = table.item(selected)["values"][0]
        role = table.item(selected)["values"][1]

        win = tk.Toplevel(parent)
        win.title("Update User")
        win.geometry("400x300")
        win.configure(bg="#F5F6F5")

        tk.Label(win, text=f"Update User: {username}", font=("Helvetica", 16, "bold"), bg="#F5F6F5").pack(pady=10)

        tk.Label(win, text="New Password:", bg="#F5F6F5", font=("Helvetica", 14)).pack()
        password_entry = tk.Entry(win, font=("Helvetica", 14), show="*")
        password_entry.pack(pady=5)

        tk.Label(win, text="Role:", bg="#F5F6F5", font=("Helvetica", 14)).pack()
        role_box = ttk.Combobox(win, values=["User", "Manager", "Drug Lord"], state="readonly", font=("Helvetica", 13))
        role_box.set(role)
        role_box.pack(pady=5)

        def save_update():
            new_pass = password_entry.get().strip()
            new_role = role_box.get()
            if not new_pass:
                messagebox.showerror("Error", "Password cannot be empty", parent=win)
                return

            cur = self.conn.cursor()
            cur.execute("UPDATE users SET password=?, role=? WHERE username=?", (new_pass, new_role, username))
            self.conn.commit()
            messagebox.showinfo("Success", "User updated successfully", parent=win)
            win.destroy()
            self.refresh_user_table(table)

        tk.Button(win, text="Save", command=save_update, bg="#4DA8DA", fg="white",
                  font=("Helvetica", 14, "bold"), relief="flat", padx=20, pady=8).pack(pady=10)
        tk.Button(win, text="Cancel", command=win.destroy, bg="#E74C3C", fg="white",
                  font=("Helvetica", 14, "bold"), relief="flat", padx=20, pady=8).pack()

    # ------------------ DELETE USER ------------------
    def delete_user(self, parent, table):
        selected = table.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a user to delete", parent=parent)
            return

        username = table.item(selected)["values"][0]
        if username == self.username:
            messagebox.showerror("Error", "You cannot delete your own account", parent=parent)
            return

        if messagebox.askyesno("Confirm Delete", f"Delete user '{username}'?", parent=parent):
            cur = self.conn.cursor()
            cur.execute("DELETE FROM users WHERE username=?", (username,))
            self.conn.commit()
            messagebox.showinfo("Deleted", "User deleted successfully", parent=parent)
            self.refresh_user_table(table)

    # ------------------ BACKUP / MAINTENANCE ------------------
    def backup_database(self):
        try:
            backup_dir = os.path.join(os.getenv("APPDATA"), "ShinanoPOS", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"pharmacy_backup_{timestamp}.db")
            shutil.copy2(self.db_path, backup_file)
            messagebox.showinfo("Backup Complete", f"Database saved to:\n{backup_file}")
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to back up database:\n{e}")

    def compact_database(self):
        try:
            cur = self.conn.cursor()
            cur.execute("VACUUM")
            self.conn.commit()
            messagebox.showinfo("Database Compacted", "Database optimized successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to compact database:\n{e}")

    def logout(self):
        self.conn.close()
        self.root.destroy()
        from login import main
        main()
