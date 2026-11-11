"""EOD-only conditional trade lifecycle reviews; no live position knowledge.

Observed high/low cannot prove a fill, a 5-minute breakout, partial booking,
or the order in which a stop/target was reached. Recommendations are scenario
instructions *for a separately confirmed fill*, never actual order changes.
"""
from __future__ import annotations

from datetime import date
from math import isfinite


# Provisional time-exit policy. Calibrate 5/7/10/15 NSE-session horizons
# using prospective or no-lookahead historical studies before claiming optimality.
DEFAULT_HOLDING_MAX_SESSIONS = 10
FIRST_REVIEW_SESSION = 5
SECOND_REVIEW_SESSION = 7
HORIZONS_FOR_VALIDATION = (5, 7, 10, 15)


def positive(value):
    try:
        value = float(value)
        return value if isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def review_research_plans(prior, asof, cash, snapshots, derivatives_trails=None):
    """Review A/B/C research plans on every available completed NSE session.

    Pending untouched entry proposals expire after two verified trading
    sessions. After a possible trigger-level touch, review an IF-FILLED
    scenario each verified NSE session. Day 5 is a progress review, day 7
    may trigger early exit on stalled weak momentum, and day 10 is the
    provisional maximum; stops, T3 and adverse evidence can end it sooner.
    No arbitrary calendar-day or five-session forced exit; all observations
    remain UNVERIFIED broker fills. Validate 5/7/10/15 holding horizons
    before claiming one is empirically superior.
    """
    updates, still_open = [], []
    derivatives_trails = derivatives_trails or {}
    for previous in prior or []:
        try:
            sig = previous["signal"]
            symbol = sig["symbol"]
            sid = sig["signal_id"]
            issued = date.fromisoformat(previous["asof_date"])
            checked = date.fromisoformat(previous.get("last_checked", previous["asof_date"]))
            if asof <= checked:
                still_open.append(previous)
                continue
            if asof <= issued:
                still_open.append(previous)
                continue
            row = cash.get(symbol)
            snapshot = snapshots.get(symbol)
            if not row or not snapshot or not snapshot.get("tech") or not snapshot.get("chain"):
                updates.append({"id":sid,"symbol":symbol,
                                "status":"REVIEW BLOCKED — CURRENT CASH / FUTURES / OPTION HISTORY INCOMPLETE",
                                "action_if_filled":"Use broker-side protective stop; no verified updated levels available",
                                "asof":asof.isoformat()})
                still_open.append({**previous,"last_checked":asof.isoformat()})
                continue
            tech, chain, future = snapshot["tech"],snapshot["chain"],snapshot["future"]
            close, high, low = [positive(row.get(k)) for k in ("ClsPric","HghPric","LwPric")]
            atr, ema = positive(tech.get("atr14")), positive(tech.get("ema20"))
            f_now = positive(future.get("SttlmPric")) or positive(future.get("ClsPric"))
            f_prev, oi_now = positive(future.get("PrvsClsgPric")), positive(future.get("OpnIntrst"))
            oi_delta = float(future.get("ChngInOpnIntrst") or 0)
            if (not all((close,high,low,atr,ema,f_now,f_prev,oi_now))
                    or high < low or (oi_now-oi_delta) <= 0):
                updates.append({"id":sid,"symbol":symbol,
                                "status":"REVIEW BLOCKED — INVALID CURRENT NSE OBSERVATIONS",
                                "action_if_filled":"Use broker-side protection; no new model stop",
                                "asof":asof.isoformat()})
                still_open.append({**previous,"last_checked":asof.isoformat()})
                continue

            side = 1 if sig["direction"]=="LONG" else -1
            entry,stop = float(sig["entry_trigger"]),float(sig["stop_loss"])
            t1,t2,t3 = (float(sig["target_"+str(n)]) for n in (1,2,3))
            if not (side*(entry-stop)>0 and side*(t1-entry)>0):
                continue
            # Daily high/low establishes only *price level* touches.
            entry_hit = (high>=entry if side>0 else low<=entry)
            # C-tier pullback/retest research must actually cross the proposed
            # level intraday. A high alone is not evidence of a pullback.
            if "pullback" in str(sig.get("entry_pattern","")).lower():
                entry_hit = entry_hit and low <= entry <= high
            stop_hit = (low<=stop if side>0 else high>=stop)
            target_hit = [(high>=target if side>0 else low<=target) for target in (t1,t2,t3)]
            first_touched = previous.get("first_entry_level_touch")
            if not first_touched and entry_hit:
                first_touched = asof.isoformat()
            pending_sessions = int(previous.get("observed_sessions",0))+1
            held_scenario = int(previous.get("hypothetical_holding_sessions",0))
            if first_touched:
                held_scenario += 1
            f_change = 100*(f_now/f_prev-1)
            oi_change = 100*(oi_now/(oi_now-oi_delta)-1)
            if f_change > .05 and oi_change > .5: regime="LONG BUILDUP"
            elif f_change < -.05 and oi_change > .5: regime="SHORT BUILDUP"
            elif f_change > .05 and oi_change < -.5: regime="SHORT COVERING"
            elif f_change < -.05 and oi_change < -.5: regime="LONG UNWINDING"
            else: regime="MIXED / NEUTRAL"
            adverse_futures = regime == ("SHORT BUILDUP" if side>0 else "LONG BUILDUP")
            aligned_futures = regime == ("LONG BUILDUP" if side>0 else "SHORT BUILDUP")
            adverse_cash = side*(close-ema) < 0
            adverse_macd = side*float(tech.get("macd_hist") or 0) < 0
            sign_close = side*(close-entry)
            fo_trail = derivatives_trails.get(symbol, [])
            # At most five prior archival FO sessions plus current. Only
            # consecutive AVAILABLE same-contract records qualify as a
            # confirmed multi-day OI direction; never interpolate gaps.
            current_valid = [i for i,obs in enumerate(fo_trail)
                             if obs.get("status")=="VERIFIED NSE FO EOD"]
            adverse_name = "SHORT BUILDUP" if side>0 else "LONG BUILDUP"
            two_day_opposing_oi = (
                len(current_valid)>=2
                and current_valid[-1]==len(fo_trail)-1
                and current_valid[-2]==len(fo_trail)-2
                and fo_trail[-1]["date"]==asof.isoformat()
                and all(fo_trail[i].get("futures_regime")==adverse_name
                        for i in current_valid[-2:])
            )
            # Apply the newest owner's provisional 10-trading-session maximum
            # even to older research plans carrying legacy 5/None metadata.
            # This is not a known broker position or independently verified
            # execution date; hold count starts on first EOD trigger touch.
            max_hold = DEFAULT_HOLDING_MAX_SESSIONS
            # Suggested new stop applies from NEXT session; never retroactively
            # pretend a newly suggested stop was active during today's candle.
            previous_suggested = positive(previous.get("suggested_stop_if_filled")) or stop
            effective_old_stop = max(stop,previous_suggested) if side>0 else min(stop,previous_suggested)
            candidate_support = (ema-side*.40*atr)
            nearest_support = positive(tech.get("prev5_low" if side>0 else "prev5_high"))
            if nearest_support:
                possible_stop = nearest_support-side*.12*atr
                candidate_support = max(candidate_support,possible_stop) if side>0 else min(candidate_support,possible_stop)
            if target_hit[0]:
                breakeven_after_cost = entry+side*.0015*entry
                candidate_support = max(candidate_support, breakeven_after_cost) if side>0 else min(candidate_support,breakeven_after_cost)
            stop_candidate = (max(effective_old_stop,candidate_support) if side>0
                              else min(effective_old_stop,candidate_support))
            # A tighter stop above/below current close would already be
            # violated, so explain EXIT/REASSESS rather than publish it.
            suggested = (round(stop_candidate,2) if side*(close-stop_candidate)>.15*atr
                         else round(effective_old_stop,2))
            # Reassess T1 if a new opposing OI wall lies between entry and old T1.
            opposing = positive(chain.get("near_call_wall" if side>0 else "near_put_wall"))
            rechecked_t1 = t1
            target_note = "Original T1/T2/T3 remain scenario levels, not automatically re-priced"
            if opposing and side*(opposing-entry)>.10*atr and side*(t1-opposing)>0:
                adjusted = opposing-side*max(.05*atr,.0005*entry)
                if side*(adjusted-entry)>.05*atr:
                    rechecked_t1 = round(adjusted,2)
                    target_note = "New opposing options wall is closer; proposed T1 is reduced (conditional, no order placed)"
            status = "NOT TRIGGERED — VERIFY LIVE 5-MIN CONDITIONS"
            action = "WAIT FOR CONFIRMED ENTRY; NO POSITION ASSUMED"
            terminal = False
            prior_model_stop_hit = (
                low <= effective_old_stop if side > 0 else high >= effective_old_stop
            )
            if stop_hit and entry_hit:
                status = "ENTRY AND STOP LEVELS TOUCHED — INTRADAY ORDER UNKNOWN"
                action = "NO AUTOMATIC HOLD; VERIFY BROKER FILLS AND STOP EXECUTION; IF STILL LONG/SHORT, REASSESS"
                terminal = True
            elif stop_hit:
                status = "ORIGINAL STOP LOSS LEVEL TOUCHED — ENTRY / FILL UNCONFIRMED"
                action = "CLOSE RESEARCH PLAN; VERIFY BROKER STOP EXECUTION AND ACTUAL POSITION STATE"
                terminal = True
            elif first_touched and prior_model_stop_hit:
                status = "PREVIOUSLY PROPOSED TRAILING-STOP LEVEL TOUCHED — UNVERIFIED EXECUTION"
                action = ("EXIT IF FILLED / CLOSE RESEARCH PLAN; suggested prior stop "
                          "may not have been placed; verify broker holdings and stop")
                terminal = True
            elif not first_touched and pending_sessions >= int(sig.get("valid_for_next_sessions",2)):
                status = "ENTRY WINDOW EXPIRED WITHOUT EOD PRICE TOUCH"
                action = "CANCEL PENDING IDEA; RESEARCH FRESH ENTRY IF STILL INTERESTING"
                terminal = True
            elif first_touched:
                ix = max((i+1 for i,x in enumerate(target_hit) if x),default=0)
                status = ("T"+str(ix)+" LEVEL TOUCHED" if ix else "ENTRY LEVEL TOUCHED")
                status += " — CASH 5-MIN CONFIRMATION / FILL UNVERIFIED"
                if adverse_futures and (adverse_cash or adverse_macd):
                    action = "EXIT IF FILLED / DO NOT INITIATE: OI REVERSAL + TECHNICAL DETERIORATION"
                    terminal = True
                elif two_day_opposing_oi and sign_close <= 0:
                    action = ("EXIT IF FILLED / DO NOT INITIATE: TWO CONSECUTIVE "
                              "VERIFIED SAME-CONTRACT OPPOSING FUTURES BUILDUP "
                              "SESSIONS, CASH PRICE NO LONGER FAVOURABLE VS ENTRY")
                    terminal = True
                elif side*(close-effective_old_stop) <= 0:
                    action = "EXIT OR REASSESS IF FILLED: PREVIOUS PROTECTIVE STOP IS BREACHED BY EOD CLOSE"
                    terminal = True
                elif target_hit[2]:
                    # T3 is the normal end of this research plan.
                    action = ("T3 PRICE LEVEL REACHED: RECOMMEND CLOSE/BOOK REMAINDER "
                              "IF FILLED. VERIFY ACTUAL BROKER ORDERS; ONLY A NEW "
                              "SEPARATE EOD TREND PLAN MAY JUSTIFY HOLDING BEYOND T3")
                    terminal = True
                elif held_scenario >= max_hold:
                    status = (f"MAXIMUM HOLDING PERIOD REACHED — {held_scenario} "
                              "TRADING-SESSION IF-FILLED SCENARIO; ACTUAL ENTRY UNVERIFIED")
                    action = ("TIME EXIT IF FILLED BY END OF TRADING SESSION 10; "
                              "CLOSE THIS RESEARCH PLAN. Do not roll the old call "
                              "forward automatically; a new separate idea needs "
                              "independent fresh entry and risk validation.")
                    terminal = True
                elif target_hit[1]:
                    action = "CONSIDER BOOKING AT T2 AND TRAIL REMAINDER IF CONFIRMED FILLED"
                elif target_hit[0]:
                    action = "CONSIDER PARTIAL EXIT AT T1; TIGHTEN STOP ONLY FOR CONFIRMED OPEN POSITION"
                elif adverse_futures or (adverse_cash and adverse_macd):
                    action = "REDUCE/EXIT IF FILLED; THESIS WEAKENING — RECHECK NEW CASH STRUCTURE AND OI"
                elif (held_scenario >= SECOND_REVIEW_SESSION
                      and sign_close < .20*abs(t1-entry)
                      and not aligned_futures):
                    action = ("EARLY EXIT IF FILLED AT DAY-7 STAGNATION REVIEW: "
                              "less than 20% of the entry-to-T1 move achieved "
                              "and no fresh aligned futures buildup.")
                    terminal = True
                elif (held_scenario >= FIRST_REVIEW_SESSION
                      and sign_close < .20*abs(t1-entry)):
                    action = ("DAY-5 PROGRESS REVIEW IF FILLED: little movement "
                              "toward T1; reassess price/OI and consider reducing; "
                              "do not hold just to reach the day-10 limit.")
                elif side*(close-entry) > 0:
                    action = "HOLD IF CONFIRMED FILLED, WITH UPDATED PROTECTIVE STOP NEXT SESSION"
                else:
                    action = "REASSESS IF FILLED; PRICE BELOW/ABOVE ENTRY AGAIN — DO NOT ADD"
            update={
                "id":sid,"symbol":symbol,"direction":sig["direction"],
                "market_date":sig.get("market_date"),"asof":asof.isoformat(),
                "status":status, "action_if_filled":action,
                "original_entry":round(entry,2),"original_stop":round(stop,2),
                "prior_suggested_stop":round(effective_old_stop,2),
                "suggested_stop_next_session_if_filled":suggested,
                "original_targets":[round(t,2) for t in (t1,t2,t3)],
                "updated_t1_if_filled":round(rechecked_t1,2),
                "target_note":target_note,
                "latest_cash_close":round(close,2),"cash_high":round(high,2),
                "cash_low":round(low,2),"price_move_from_entry_pct":round(100*sign_close/entry,2),
                "futures_regime_today":regime,"futures_price_change_pct":round(f_change,2),
                "futures_oi_change_pct":round(oi_change,2),
                "ema20":round(ema,2),"rsi14":round(float(tech.get("rsi14") or 0),1),
                "macd_hist":round(float(tech.get("macd_hist") or 0),4),
                "opposing_oi_wall":opposing,
                "historical_fo_sessions_provided":len(fo_trail),
                "two_verified_consecutive_adverse_futures_oi_days":two_day_opposing_oi,
                "observed_sessions_since_signal":pending_sessions,
                "hypothetical_holding_sessions":held_scenario if first_touched else 0,
                "entry_price_level_ever_touched":bool(first_touched),
                "entry_confirmed":False,"fill_status":"UNKNOWN — no broker fills supplied",
                "lifecycle_policy":"Review on day 5, consider early exit at day 7 if stalled; mandatory scenario time exit by day 10 if SL/T3/other evidence has not closed it; trading sessions only",
                "provisional_max_holding_sessions":max_hold,
                "time_checkpoints":[FIRST_REVIEW_SESSION,SECOND_REVIEW_SESSION],
                "comparison_horizons_sessions":list(HORIZONS_FOR_VALIDATION),
                "hypothetical_sessions_remaining":(max(0,max_hold-held_scenario)
                    if first_touched else None),
                "closure_reason":action if terminal else None,
                "actual_position_known":False,"terminal_for_scenario":terminal,
                "data_quality":"Current-session NSE cash, futures, option chain and technicals",
                "risk_note":"EOD data cannot establish intraday event sequence or a broker fill. Proposed changes start NEXT session only."
            }
            updates.append(update)
            if not terminal:
                still_open.append({**previous,"last_checked":asof.isoformat(),
                                   "observed_sessions":pending_sessions,
                                   "first_entry_level_touch":first_touched,
                                   "hypothetical_holding_sessions":held_scenario,
                                   "suggested_stop_if_filled":suggested})
        except (KeyError,ValueError,TypeError,OverflowError) as exc:
            # Never silently lose older plans just because a legacy proposal
            # lacks T3, a field changed, or a row has non-numeric content.
            signal=previous.get("signal",{}) if isinstance(previous,dict) else {}
            sid=signal.get("signal_id","UNIDENTIFIED-RESEARCH-PLAN")
            symbol=signal.get("symbol","UNKNOWN")
            updates.append({"id":sid,"symbol":symbol,"asof":asof.isoformat(),
                            "status":"REVIEW BLOCKED — INVALID/INCOMPLETE PRIOR SIGNAL DATA",
                            "action_if_filled":"Use existing broker protection; review/repair original idea data before suggesting changed levels",
                            "reason":str(exc)[:150],"entry_confirmed":False,
                            "actual_position_known":False})
            still_open.append(previous)
    return updates,still_open
