def display_name(user):
    """日本式(姓 名)の表示名。氏名未設定ならユーザー名。"""
    if not user:
        return "未割当"
    full = f"{user.last_name} {user.first_name}".strip()
    return full or user.username
