from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AppUser(db.Model):
    __tablename__ = 'app_users'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role     = db.Column(db.String(10), default='user')  # admin / user
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def set_password(self, pw):
        self.password = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password, pw)


class Client(db.Model):
    __tablename__ = 'clients'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('app_users.id'))
    name          = db.Column(db.String(50), nullable=False)       # 何小名
    name_masked   = db.Column(db.String(50), nullable=False)       # 何O名
    risk_profile  = db.Column(db.String(20))                       # 保守 / 穩健 / 積極
    tags          = db.Column(db.Text)                             # JSON list: ["半導體","收息"]
    notes         = db.Column(db.Text)                             # 備註（理專自己看）
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    positions     = db.relationship('Position', back_populates='client', lazy=True)

    @staticmethod
    def mask_name(name):
        if not name or len(name) < 2:
            return name
        return name[0] + 'O' + name[2:]

    @property
    def tags_list(self):
        """tags JSON 字串 → list"""
        if not self.tags:
            return []
        try:
            import json
            return json.loads(self.tags)
        except Exception:
            return []


class Product(db.Model):
    __tablename__ = 'products'
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('app_users.id'))
    product_code   = db.Column(db.String(20), nullable=False)
    issuer         = db.Column(db.String(20))
    product_type   = db.Column(db.String(10), default='FCN')
    tenor_months   = db.Column(db.Integer)
    currency       = db.Column(db.String(5), default='USD')
    coupon_rate    = db.Column(db.Float)                          # 0.12 = 12%
    trade_date     = db.Column(db.Date)
    start_date     = db.Column(db.Date)                          # 比價日 = KO 觀察起始日
    maturity_date  = db.Column(db.Date)                          # 期末訂價日
    ko_pct         = db.Column(db.Float)                         # 1.00 = 100%
    strike_pct     = db.Column(db.Float)
    eki_pct        = db.Column(db.Float)                         # None = 無EKI
    ko_type        = db.Column(db.String(20), default='fixed')   # fixed / stepdown
    ko_lockout     = db.Column(db.Integer, default=1)            # 閉鎖期（月）
    ko_start_pct   = db.Column(db.Float)                         # stepdown 起始KO，如 0.98 = 98%
    ko_stepdown_pct = db.Column(db.Float)                        # 每月遞減，如 0.03 = 3%
    observation_dates = db.Column(db.Text)                       # 比價日 JSON，如 ["2025-11-14","2025-12-15",...]
    special_notes  = db.Column(db.Text)
    status         = db.Column(db.String(20), default='active')  # active / ko_exited / matured
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    underlyings    = db.relationship('Underlying', back_populates='product',
                                     cascade='all, delete-orphan', lazy=True)
    positions      = db.relationship('Position', back_populates='product', lazy=True)
    payment_schedule = db.relationship('PaymentSchedule', back_populates='product',
                                       cascade='all, delete-orphan', lazy=True,
                                       order_by='PaymentSchedule.period')

    @property
    def days_to_maturity(self):
        if self.maturity_date:
            return (self.maturity_date - date.today()).days
        return None

    @property
    def all_ko_hit(self):
        uls = [u for u in self.underlyings if u.initial_price]
        return len(uls) > 0 and all(u.ko_hit for u in uls)

    @property
    def is_ko_observing(self):
        """今天是否已進入 KO 觀察期（start_date = 比價日 = KO 觀察起始日）"""
        if not self.start_date:
            return False
        return date.today() >= self.start_date

    @property
    def next_payment(self):
        """下一個還沒過配息日的 PaymentSchedule 列；都過了傳 None"""
        today = date.today()
        for s in sorted(self.payment_schedule, key=lambda x: x.period):
            if s.payment_date and s.payment_date >= today:
                return s
        return None

    @property
    def paid_count(self):
        """已過配息日的期數（payment_date < today）"""
        today = date.today()
        return sum(1 for s in self.payment_schedule if s.payment_date and s.payment_date < today)

    @property
    def total_periods(self):
        return len(self.payment_schedule)


class Underlying(db.Model):
    __tablename__ = 'underlyings'
    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    ticker         = db.Column(db.String(20), nullable=False)
    initial_price  = db.Column(db.Float)
    ko_level       = db.Column(db.Float)
    strike_level   = db.Column(db.Float)
    eki_level      = db.Column(db.Float)
    ko_hit         = db.Column(db.Boolean, default=False)
    ko_hit_date    = db.Column(db.Date)                    # 記憶式出場：鎖定日期
    latest_price   = db.Column(db.Float)
    price_date     = db.Column(db.Date)
    position_order = db.Column(db.Integer)
    product        = db.relationship('Product', back_populates='underlyings')


class PaymentSchedule(db.Model):
    """配息排程表 — 記錄每期觀察起訖、配息日、是否已配"""
    __tablename__ = 'payment_schedules'
    id              = db.Column(db.Integer, primary_key=True)
    product_id      = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    period          = db.Column(db.Integer, nullable=False)        # 1, 2, 3...
    obs_start_date  = db.Column(db.Date)                           # 觀察期間起始日（含）
    obs_end_date    = db.Column(db.Date)                           # 觀察期間結束日（含）
    payment_date    = db.Column(db.Date, nullable=False)           # 配息給付日
    paid            = db.Column(db.Boolean, default=False)         # 是否已配（自動：今天 > 配息日）
    product         = db.relationship('Product', back_populates='payment_schedule')
    __table_args__ = (db.UniqueConstraint('product_id', 'period'),)

    @property
    def status(self):
        """已配 / 下次配息 / 未到 — 由 view 端使用"""
        today = date.today()
        if self.payment_date < today:
            return 'paid'
        elif self.payment_date == today:
            return 'today'
        else:
            return 'future'


class Position(db.Model):
    __tablename__ = 'positions'
    id                = db.Column(db.Integer, primary_key=True)
    client_id         = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    product_id        = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    investment_amount = db.Column(db.Float)                      # USD金額
    notes             = db.Column(db.Text)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    client            = db.relationship('Client', back_populates='positions')
    product           = db.relationship('Product', back_populates='positions')

    @property
    def monthly_coupon(self):
        if self.investment_amount and self.product and self.product.coupon_rate:
            return round(self.investment_amount * self.product.coupon_rate / 12, 2)
        return None


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('app_users.id'))
    username   = db.Column(db.String(50))
    action     = db.Column(db.String(200))
    ip         = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    id             = db.Column(db.Integer, primary_key=True)
    underlying_id  = db.Column(db.Integer, db.ForeignKey('underlyings.id'), nullable=False)
    price_date     = db.Column(db.Date, nullable=False)
    closing_price  = db.Column(db.Float)
    ko_triggered   = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint('underlying_id', 'price_date'),)
