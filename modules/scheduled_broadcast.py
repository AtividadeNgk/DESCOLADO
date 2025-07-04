import asyncio
import json
from datetime import datetime, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import modules.manager as manager
from datetime import datetime, time, timezone, timedelta
import pytz

# Dicionário global para armazenar tasks ativas
active_broadcast_tasks = {}

async def send_scheduled_broadcast(context, broadcast_config, bot_id):
    """Envia um disparo programado para todos os usuários"""
    try:
        # Pega todos os usuários do bot
        users = manager.get_bot_users(bot_id)
        if not users:
            return
        
        # Pega os planos do bot
        planos = manager.get_bot_plans(bot_id)
        if not planos:
            return
        
        # Calcula o desconto
        desconto = broadcast_config['discount']
        
        print(f"[DISPARO PROGRAMADO] Iniciando disparo {broadcast_config['id']} para {len(users)} usuários")
        
        enviados = 0
        erros = 0
        
        for user_id in users:
            try:
                # Monta os botões dos planos com desconto
                keyboard_plans = []
                for plan_index in range(len(planos)):
                    plano = planos[plan_index]
                    valor_original = plano['value']
                    valor_com_desconto = valor_original * (1 - desconto / 100)
                    
                    # Formata o botão
                    botao_texto = f"{plano['name']} - R$ {valor_com_desconto:.2f} ({int(desconto)}% OFF)"
                    
                    # Cria um plano modificado para o pagamento
                    plano_broadcast = plano.copy()
                    plano_broadcast['value'] = valor_com_desconto
                    plano_broadcast['is_scheduled_broadcast'] = True
                    plano_broadcast['original_value'] = valor_original
                    plano_broadcast['discount'] = desconto
                    
                    # Cria o pagamento com o plano modificado
                    payment_id = manager.create_payment(user_id, plano_broadcast, f"{plano['name']} - Broadcast", bot_id)
                    
                    # Gera PIX direto
                    keyboard_plans.append([InlineKeyboardButton(botao_texto, callback_data=f"pagar_{payment_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard_plans)
                
                # Envia a mensagem
                if broadcast_config['media']:
                    if broadcast_config['text']:
                        if broadcast_config['media']['type'] == 'photo':
                            await context.bot.send_photo(
                                chat_id=user_id,
                                photo=broadcast_config['media']['file'],
                                caption=broadcast_config['text'],
                                reply_markup=reply_markup
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=user_id,
                                video=broadcast_config['media']['file'],
                                caption=broadcast_config['text'],
                                reply_markup=reply_markup
                            )
                    else:
                        if broadcast_config['media']['type'] == 'photo':
                            await context.bot.send_photo(
                                chat_id=user_id,
                                photo=broadcast_config['media']['file'],
                                reply_markup=reply_markup
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=user_id,
                                video=broadcast_config['media']['file'],
                                reply_markup=reply_markup
                            )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=broadcast_config.get('text', 'Oferta especial!'),
                        reply_markup=reply_markup
                    )
                
                enviados += 1
                
                # Delay entre mensagens para evitar flood
                await asyncio.sleep(0.05)
                
            except Exception as e:
                erros += 1
                print(f"Erro ao enviar para {user_id}: {e}")
        
        print(f"[DISPARO PROGRAMADO] Finalizado - Enviados: {enviados}, Erros: {erros}")
        
    except Exception as e:
        print(f"Erro no disparo programado: {e}")

async def broadcast_scheduler(context, broadcast_config, bot_id):
    """Agenda e executa disparos no horário configurado (Horário de Brasília)"""
    # Define timezone de Brasília
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    
    while True:
        try:
            # Pega o horário atual em Brasília
            now_brasilia = datetime.now(brasilia_tz)
            
            # Pega o horário configurado
            hora, minuto = map(int, broadcast_config['time'].split(':'))
            
            # Cria o datetime alvo para hoje em Brasília
            target_time_brasilia = now_brasilia.replace(
                hour=hora, 
                minute=minuto, 
                second=0, 
                microsecond=0
            )
            
            # Se já passou o horário hoje, agenda para amanhã
            if target_time_brasilia <= now_brasilia:
                target_time_brasilia += timedelta(days=1)
            
            # Calcula tempo de espera
            wait_seconds = (target_time_brasilia - now_brasilia).total_seconds()
            
            print(f"[DISPARO PROGRAMADO] Broadcast {broadcast_config['id']} agendado para {target_time_brasilia.strftime('%d/%m/%Y %H:%M')} (Horário de Brasília)")
            print(f"[DISPARO PROGRAMADO] Aguardando {wait_seconds/60:.1f} minutos")
            
            # Aguarda até o horário
            await asyncio.sleep(wait_seconds)
            
            # Executa o disparo
            await send_scheduled_broadcast(context, broadcast_config, bot_id)
            
            # Aguarda 60 segundos para evitar duplicação
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            print(f"[DISPARO PROGRAMADO] Task cancelada para broadcast {broadcast_config['id']}")
            break
        except Exception as e:
            print(f"Erro no scheduler: {e}")
            await asyncio.sleep(60)  # Espera 1 minuto antes de tentar novamente

def start_scheduled_broadcasts_for_bot(context, bot_id):
    """Inicia todos os disparos programados de um bot"""
    broadcasts = manager.get_bot_scheduled_broadcasts(bot_id)
    
    # Cancela tasks antigas se existirem
    bot_key = f"bot_{bot_id}"
    if bot_key in active_broadcast_tasks:
        for task in active_broadcast_tasks[bot_key]:
            task.cancel()
        active_broadcast_tasks[bot_key] = []
    else:
        active_broadcast_tasks[bot_key] = []
    
    # Cria novas tasks
    for broadcast in broadcasts:
        task = asyncio.create_task(broadcast_scheduler(context, broadcast, bot_id))
        active_broadcast_tasks[bot_key].append(task)
        print(f"[DISPARO PROGRAMADO] Iniciado broadcast {broadcast['id']} para bot {bot_id}")

def stop_scheduled_broadcasts_for_bot(bot_id):
    """Para todos os disparos programados de um bot"""
    bot_key = f"bot_{bot_id}"
    if bot_key in active_broadcast_tasks:
        for task in active_broadcast_tasks[bot_key]:
            task.cancel()
        del active_broadcast_tasks[bot_key]
        print(f"[DISPARO PROGRAMADO] Parados todos os broadcasts do bot {bot_id}")