import asyncio
import logging
import time
import os
import uuid
import firebase_admin
from firebase_admin import credentials, db as firebase_db
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, 
    InlineKeyboardButton, WebAppInfo, MenuButtonWebApp, Message, CallbackQuery, FSInputFile
)

# --- ১. Firebase কানেকশন সেটআপ ---
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://bachelor-point-season-5-default-rtdb.firebaseio.com/' 
})

# --- ২. ট্রাফিক পুলিশ (Rate Limiter) ---
class TrafficPoliceMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 25):
        self.limit = limit
        self.request_times = []
        super().__init__()

    async def __call__(self, handler, event, data):
        current_time = time.time()
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        if len(self.request_times) >= self.limit:
            await asyncio.sleep(0.2)
            return await self.__call__(handler, event, data)
        self.request_times.append(current_time)
        return await handler(event, data)

# --- ৩. কনফিগারেশন ---
TOKEN = "8546964452:AAEEP6qKc-AxRFxXlEX1I7YOD-BR-r_rxVU" 
ADMIN_LIST = [6856009995, 8250011268] 
WEB_APP_URL = "https://mizanurrahman-aas.pages.dev/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.message.outer_middleware(TrafficPoliceMiddleware(limit=25))

# --- ৪. States ---
class VideoUpload(StatesGroup):
    name = State()
    photo = State()
    category = State()
    video_source = State()

class VideoDelete(StatesGroup):
    waiting_for_search = State()
    confirm_selection = State()

class BotNotice(StatesGroup):
    waiting_for_payload = State()

# --- ৫. কিবোর্ড ফাংশনসমূহ ---
def get_admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Add Video"), KeyboardButton(text="🔕 Delete Video")],
        [KeyboardButton(text="📢 BOT NOTICE"), KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

def get_back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Back to Menu")]], resize_keyboard=True)

def get_category_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="BP S5")],
        [KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

# --- ৬. সাপ্তাহিক অটোমেটিক ব্যাকআপ ফাংশন ---
async def send_weekly_backup():
    while True:
        await asyncio.sleep(604800) 
        for admin_id in ADMIN_LIST:
            try:
                data = firebase_db.reference('/').get()
                backup_filename = "firebase_backup.json"
                with open(backup_filename, "w", encoding="utf-8") as f:
                    import json
                    json.dump(data, f, indent=4)
                
                db_file = FSInputFile(backup_filename)
                await bot.send_document(
                    chat_id=admin_id, 
                    document=db_file, 
                    caption=f"📅 <b>সাপ্তাহিক ক্লাউড ব্যাকআপ রিপোর্ট</b>\n\n✅ আপনার ফায়ারবেস ডাটাবেজটি ক্লাউড থেকে সরাসরি পাঠানো হয়েছে।"
                )
            except Exception as e:
                logging.error(f"Backup failed for {admin_id}: {e}")

# --- ৭. মেইন স্টার্ট হ্যান্ডলার ---
@dp.message(CommandStart())
@dp.message(F.text == "🔙 Back to Menu")
async def start_handler(message: Message, command: CommandObject = None, state: FSMContext = None):
    if state: await state.clear()
    user_id = str(message.from_user.id)
    
    user_ref = firebase_db.reference(f'users/{user_id}')
    if not user_ref.get():
        user_ref.set({'joined_at': time.time()})

    await bot.set_chat_menu_button(
        chat_id=int(user_id), 
        menu_button=MenuButtonWebApp(text="Watch Now 🎬", web_app=WebAppInfo(url=WEB_APP_URL))
    )

    if command and command.args:
        video_id = command.args
        v_data = firebase_db.reference(f'videos/{video_id}').get()
        
        if v_data:
            await bot.send_video(
                chat_id=int(user_id), 
                video=v_data['video'], 
                caption=f"🎬 <b>{v_data['name']}</b>\n\nআপনার ভিডিওটি নিচে দেওয়া হলো। উপভোগ করুন!", 
                parse_mode="HTML",
                protect_content=True
            )
            return

    user_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Watch Now (Web App)", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

    welcome_text = (
        "<b>আসসালামুয়ালাইকুম</b> 🥰\n\n"
        "আমাদের বট ২৪ ঘন্টা সচল। ভিডিও ডাউনলোড করতে নিচের <b>Watch Now</b> বাটনে ক্লিক করুন 🥰"
    )

    await message.answer(
        welcome_text,
        reply_markup=user_kb,
        parse_mode="HTML"
    )
    
    if int(user_id) in ADMIN_LIST:
        await message.answer("🛠 এডমিন প্যানেল সচল করা হয়েছে:", reply_markup=get_admin_kb())

# --- ৮. ভিডিও অ্যাড করার লজিক ---
@dp.message(F.text == "➕ Add Video")
async def add_v_start(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoUpload.name)
        await message.answer("📝 ভিডিওর টাইটেল লিখুন (উদাঃ Episode 01):", reply_markup=get_back_kb())

@dp.message(VideoUpload.name)
async def add_v_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(VideoUpload.photo)
    await message.answer("🖼 থাম্বনেইল পাঠান (সরাসরি ফটো অথবা ইউআরএল):", reply_markup=get_back_kb())

@dp.message(VideoUpload.photo)
async def add_v_photo(message: Message, state: FSMContext):
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        await state.update_data(photo=photo_url)
    else:
        await state.update_data(photo=message.text)
    
    await state.set_state(VideoUpload.category)
    await message.answer("📂 ক্যাটাগরি সিলেক্ট করুন:", reply_markup=get_category_kb())

@dp.message(VideoUpload.category)
async def add_v_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(VideoUpload.video_source)
    await message.answer("🎬 এখন ভিডিও ফাইলটি (Telegram Video) পাঠান:", reply_markup=get_back_kb())

@dp.message(VideoUpload.video_source, F.video)
async def add_v_final(message: Message, state: FSMContext):
    data = await state.get_data()
    v_id = str(uuid.uuid4())[:8]
    
    firebase_db.reference(f'videos/{v_id}').set({
        'id': v_id,
        'name': data['name'],
        'photo': data['photo'],
        'ad_count': 0,
        'video': message.video.file_id,
        'category': data['category']
    })
    
    await message.answer(f"✅ ভিডিও সফলভাবে যুক্ত হয়েছে!\nআইডি: `{v_id}`", parse_mode="Markdown", reply_markup=get_admin_kb())
    await state.clear()

# --- ৯. ভিডিও ডিলিট করার লজিক ---
@dp.message(F.text == "🔕 Delete Video")
async def delete_v_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoDelete.waiting_for_search)
        await message.answer("🔍 ডিলিট করতে চাওয়া ভিডিওর নাম লিখুন:", reply_markup=get_back_kb())

@dp.message(VideoDelete.waiting_for_search)
async def delete_v_search_results(message: Message, state: FSMContext):
    query = message.text.lower()
    videos_ref = firebase_db.reference('videos').get()
    
    if not videos_ref:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return

    matches = [v for v in videos_ref.values() if query in v['name'].lower()]
    
    if not matches:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return

    buttons = [[InlineKeyboardButton(text=f"🗑 {v['name']}", callback_data=f"ask_del:{v['id']}")] for v in matches]
    buttons.append([InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel_del")])
    await message.answer(f"🔎 {len(matches)}টি ভিডিও পাওয়া গেছে। কোনটি মুছবেন?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(VideoDelete.confirm_selection)

@dp.callback_query(F.data.startswith("ask_del:"), VideoDelete.confirm_selection)
async def delete_v_confirm(callback: CallbackQuery):
    vid_id = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ হ্যা, ডিলিট করুন", callback_data=f"do_del:{vid_id}")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="cancel_del")]
    ])
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে এই ভিডিওটি মুছতে চান?", reply_markup=kb)

@dp.callback_query(F.data.startswith("do_del:"), VideoDelete.confirm_selection)
async def delete_v_execute(callback: CallbackQuery, state: FSMContext):
    vid_id = callback.data.split(":")[1]
    firebase_db.reference(f'videos/{vid_id}').delete()
    await callback.message.edit_text("✅ ভিডিওটি সফলভাবে মুছে ফেলা হয়েছে।")
    await state.clear()

@dp.callback_query(F.data == "cancel_del")
async def delete_v_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚫 অপারেশন বাতিল করা হয়েছে।")
    await state.clear()

# --- ১০. ব্রডকাস্ট নোটিশ (সংশোধিত লজিক) ---
@dp.message(F.text == "📢 BOT NOTICE")
async def notice_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(BotNotice.waiting_for_payload)
        await message.answer("📢 নোটিশ মেসেজটি দিন (টেক্সট/ছবি/ভিডিও):", reply_markup=get_back_kb())

@dp.message(BotNotice.waiting_for_payload)
async def notice_broadcast(message: Message, state: FSMContext):
    users_ref = firebase_db.reference('users').get()
    if not users_ref:
        await message.answer("❌ কোনো ইউজার পাওয়া যায়নি।")
        await state.clear()
        return

    progress_msg = await message.answer("⏳ ব্রডকাস্ট শুরু হচ্ছে...")
    count = 0
    total_users = len(users_ref)
    
    # ব্রডকাস্টিংয়ের সময় ১৫ জনের লিমিট কার্যকর থাকবে এবং প্রতি সেকেন্ডে ১০ জন করে যাবে
    dp.message.outer_middleware["TrafficPoliceMiddleware"].limit = 15
    
    for i, uid in enumerate(users_ref.keys()):
        try: 
            await message.copy_to(chat_id=int(uid))
            count += 1
            
            # প্রতি ১০টি মেসেজ পাঠানোর পর ১ সেকেন্ড বিরতি (টেলিগ্রাম লিমিট রক্ষার জন্য)
            if count % 10 == 0:
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(0.05) # সাধারণ ডিলে
                
        except Exception:
            continue
            
    # ব্রডকাস্ট শেষ হলে লিমিট পুনরায় ২৫ করে দেওয়া হলো
    dp.message.outer_middleware["TrafficPoliceMiddleware"].limit = 25
    
    await progress_msg.delete()
    await message.answer(f"📢 রিপোর্ট: ✅ {count}/{total_users} জন সফল।", reply_markup=get_admin_kb())
    await state.clear()

# --- ১১. মেইন রানার ---
async def main():
    print("🤖 Bot is Starting with Firebase Cloud Database...")
    asyncio.create_task(send_weekly_backup())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
