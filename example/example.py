from numba import njit
import pandas as pd

from hftbacktest import NONE, NEW, HftBacktest, GTX, FeedLatency, BUY, SELL, Linear


@njit
def market_making_algo(hbt):
    a = 1
    b = 1
    c = 1
    hs = 1

    # alpha, it can be a combination of several indicators.
    forecast = 0
    # in hft, it could be a measurement of short-term market movement such as high - low of the last x-min.
    volatility = 0
    max_notional_position = 1000
    notional_qty = 100

    while hbt.run:
        # in microseconds
        if not hbt.elapse(0.1 * 1e6):
            return False
        hbt.clear_inactive_orders()

        """
        You can find the core ideas from the following articles.
        https://ieor.columbia.edu/files/seasdepts/industrial-engineering-operations-research/pdf-files/Borden_D_FESeminar_Sp10.pdf (page 5)
        https://arxiv.org/abs/1105.3115 (the last three equations on page 13 and 7 Backtests)
        https://blog.bitmex.com/wp-content/uploads/2019/11/Algo-Trading-and-Market-Making.pdf
        https://www.wikijob.co.uk/trading/forex/market-making

        Also see my other repo.
        """
        # delta risk, it also can be a combination of several risks.
        risk = (c + volatility) * hbt.position
        half_spread = (c + volatility) * hs

        mid = (hbt.best_bid + hbt.best_ask) / 2.0

        # fair value pricing = mid + a * forecast
        #                      or underlying(correlated asset) + adjustment(basis + cost + etc) + a * forecast
        # risk skewing = -b * risk
        new_bid = mid + a * forecast - b * risk - half_spread
        new_ask = mid + a * forecast - b * risk + half_spread

        new_bid_tick = round(new_bid / hbt.tick_size)
        new_ask_tick = round(new_ask / hbt.tick_size)

        new_bid = new_bid_tick * hbt.tick_size
        new_ask = new_ask_tick * hbt.tick_size
        order_qty = round(notional_qty / mid / hbt.lot_size) * hbt.lot_size

        # Elapse a process time
        if not hbt.elapse(.05 * 1e6):
            return False

        last_order_id = -1
        update_bid = True
        update_ask = True
        for order in hbt.orders.values():
            if order.side == BUY:
                if round(order.price / hbt.tick_size) == new_bid_tick \
                        or hbt.position * mid > max_notional_position:
                    update_bid = False
                elif order.cancellable:
                    hbt.cancel(order.order_id)
                    last_order_id = order.order_id
            if order.side == SELL:
                if round(order.price / hbt.tick_size) == new_ask_tick \
                        or hbt.position * mid < -max_notional_position:
                    update_ask = False
                if order.cancellable or hbt.position * mid < -max_notional_position:
                    hbt.cancel(order.order_id)
                    last_order_id = order.order_id

        # It can be combined with grid trading strategy by sumitting multiple orders to capture the better spread.
        # Then, it needs a more sophiscated logic to efficiently maintain resting orders in the book.
        if update_bid:
            # There is only one order on a given price, use new_bid_tick as order Id.
            hbt.submit_buy_order(new_bid_tick, new_bid, order_qty, GTX)
            last_order_id = new_bid_tick
        if update_ask:
            # There is only one order on a given price, use new_ask_tick as order Id.
            hbt.submit_sell_order(new_ask_tick, new_ask, order_qty, GTX)
            last_order_id = new_ask_tick

        # All order requests are considered to be requested at the same time.
        # Wait until one of the order responses is received.
        if last_order_id >= 0 and not hbt.wait_order_response(last_order_id):
            return False

        print(hbt.local_timestamp, mid, hbt.position, hbt.position * mid + hbt.balance - hbt.fee)
    return True


if __name__ == '__main__':
    # data file
    # https://github.com/nkaz001/collect-binancefutures

    # This backtest assumes market maker rebates.
    # https://www.binance.com/en/support/announcement/5d3a662d3ace4132a95e77f6ab0f5422
    snapshot_df = pd.read_pickle('../../btcusdt_20220830.snapshot.pkl', compression='gzip')

    hbt = HftBacktest(['../../btcusdt_20220831.pkl', '../../btcusdt_20220901.pkl'],
                      tick_size=0.1,
                      lot_size=0.001,
                      maker_fee=-0.00005,
                      taker_fee=0.0007,
                      order_latency=FeedLatency(1),
                      asset_type=Linear,
                      snapshot=snapshot_df)
    market_making_algo(hbt)
