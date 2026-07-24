from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
)


class RegistrationForm(FlaskForm):
    username = StringField(
        "아이디",
        validators=[
            DataRequired(),
            Length(min=4, max=20),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="아이디는 영문, 숫자, 밑줄만 사용할 수 있습니다.",
            ),
        ],
    )
    display_name = StringField(
        "표시 이름", validators=[DataRequired(), Length(min=2, max=60)]
    )
    password = PasswordField(
        "비밀번호", validators=[DataRequired(), Length(min=10, max=128)]
    )
    password_confirm = PasswordField(
        "비밀번호 확인",
        validators=[
            DataRequired(),
            EqualTo("password", message="비밀번호가 일치하지 않습니다."),
        ],
    )
    bio = TextAreaField("소개글", validators=[Optional(), Length(max=300)])
    submit = SubmitField("회원가입")


class LoginForm(FlaskForm):
    username = StringField("아이디", validators=[DataRequired(), Length(min=4, max=20)])
    password = PasswordField(
        "비밀번호", validators=[DataRequired(), Length(min=10, max=128)]
    )
    submit = SubmitField("로그인")


class ProfileForm(FlaskForm):
    display_name = StringField(
        "표시 이름", validators=[DataRequired(), Length(min=2, max=60)]
    )
    bio = TextAreaField("소개글", validators=[Optional(), Length(max=300)])
    new_password = PasswordField(
        "새 비밀번호", validators=[Optional(), Length(min=10, max=128)]
    )
    confirm_new_password = PasswordField(
        "새 비밀번호 확인",
        validators=[
            Optional(),
            EqualTo("new_password", message="새 비밀번호가 일치하지 않습니다."),
        ],
    )
    submit = SubmitField("프로필 수정")


class ProductForm(FlaskForm):
    title = StringField("상품명", validators=[DataRequired(), Length(min=2, max=80)])
    category = StringField(
        "카테고리", validators=[DataRequired(), Length(min=2, max=40)]
    )
    description = TextAreaField(
        "상품 설명", validators=[DataRequired(), Length(min=10, max=1200)]
    )
    price = DecimalField(
        "가격",
        validators=[DataRequired(), NumberRange(min=0.01, max=100000000)],
        places=2,
    )
    status = SelectField(
        "상태",
        choices=[
            ("available", "판매중"),
            ("reserved", "예약중"),
            ("sold", "판매완료"),
        ],
        validators=[DataRequired()],
    )
    image = FileField(
        "상품 이미지",
        validators=[
            Optional(),
            FileAllowed(
                ["jpg", "jpeg", "png", "gif", "webp"],
                "이미지 파일만 업로드할 수 있습니다.",
            ),
        ],
    )
    submit = SubmitField("저장")


class ReportForm(FlaskForm):
    reason = TextAreaField(
        "신고 사유", validators=[DataRequired(), Length(min=10, max=500)]
    )
    submit = SubmitField("신고 접수")


class TransferForm(FlaskForm):
    recipient_username = StringField(
        "받는 사람 아이디", validators=[DataRequired(), Length(min=4, max=20)]
    )
    amount = DecimalField(
        "송금 금액",
        validators=[DataRequired()],
        places=2,
    )
    note = StringField("메모", validators=[Optional(), Length(max=160)])
    submit = SubmitField("송금")


class WithdrawalForm(FlaskForm):
    password = PasswordField(
        "현재 비밀번호", validators=[DataRequired(), Length(min=10, max=128)]
    )
    confirmation = StringField(
        "확인 문구",
        validators=[
            DataRequired(),
            Regexp(r"^탈퇴$", message="확인 문구로 '탈퇴'를 정확히 입력하세요."),
        ],
    )
    submit = SubmitField("회원 탈퇴")
