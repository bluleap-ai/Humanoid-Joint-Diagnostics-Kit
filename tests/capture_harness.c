/* Runs the actual capture.c against a deterministic, single-thread HAL fake.
 * This tests application state/queue logic, not Zephyr scheduling or hardware.
 */
#include "../firmware/src/capture.c"
#include <assert.h>
int main(void) {
    assert(capture_init() == 0);
    assert(fake_silent == 1);
    assert(!applied.active);
    struct w_frame tx = {.id = 1, .dlc = 1, .len = 1, .data = {7}};
    assert(capture_tx(&tx, 10, 2, 10) == -EPERM);
    assert(capture_start() == 0);
    assert(fake_mode & CAN_MODE_LISTENONLY);
    struct can_frame incoming = {.id = 42, .dlc = 1, .data = {1}};
    for (int i = 0; i < 5; i++)
        rx(can, &incoming, 0);
    assert(received == 5 && enqueued == 2 && drops == 3 && sequence == 5 && highwater == 2);
    incoming.data[0] = 99; /* queued records must own their payload */
    struct w_frame r;
    assert(!k_msgq_get(&rx_queue, &r, 0));
    assert(r.seq == 1);
    assert(r.data[0] == 1);
    assert(!k_msgq_get(&rx_queue, &r, 0));
    assert(r.seq == 2);
    rx(can, &incoming, 0);
    assert(!k_msgq_get(&rx_queue, &r, 0));
    assert(r.seq == 6);
    struct capture_config cfg = applied;
    cfg.active = true;
    cfg.fd = true;
    assert(!capture_configure(&cfg));
    assert(!capture_start());
    assert(fake_silent == 0);
    assert(!(fake_mode & CAN_MODE_LISTENONLY));
    assert(!capture_tx(&tx, 10, 2, 10));
    assert(capture_tx(&tx, 10, 2, 11) == -EBUSY);
    scheduler_tick();
    assert(fake_sends == 1 && inflight);
    fake_done(can, 0, 0);
    fake_done = 0;
    scheduler_tick();
    assert(completed == 1);
    fake_now = 10;
    scheduler_tick();
    assert(fake_sends == 2);
    capture_stop();
    assert(fake_silent == 1 && !inflight && !scheduled && !applied.active);
    assert(!capture_start());
    assert(fake_mode & CAN_MODE_LISTENONLY); /* regression: no implicit active restart */
    fake_now += 3001;
    scheduler_tick();
    assert(!running && fake_silent);
    cfg.sp = 876;
    assert(capture_configure(&cfg) < 0);
    assert(capture_start() < 0);
    cfg.sp = 875;
    assert(!capture_configure(&cfg));
    assert(!capture_start());
    assert(!capture_tx(&tx, 10, 2, 12));
    scheduler_tick();
    fake_now += 1001;
    scheduler_tick();
    assert(!running && !scheduled && !inflight); /* hung TX is indeterminate and disabled */
    puts("capture application state tests passed");
}
