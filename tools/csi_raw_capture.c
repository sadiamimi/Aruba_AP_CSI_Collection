#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/netlink.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>

enum {
    CSI_NETLINK_MESSAGE_BYTES = 8208,
    CSI_NETLINK_HEADER_BYTES = NLMSG_HDRLEN,
    CSI_PAYLOAD_BYTES = 8192,
    CSI_HPE_WORDS_PER_LINE = 8,
    CSI_HPE_TEXT_RECORD_BYTES = 12 + (CSI_PAYLOAD_BYTES / 4) * 11
                                + (CSI_PAYLOAD_BYTES / 32),
};

static volatile sig_atomic_t stop_requested;

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static int write_all(int fd, const unsigned char *data, size_t length)
{
    while (length > 0) {
        ssize_t written = write(fd, data, length);
        if (written < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        data += written;
        length -= (size_t)written;
    }
    return 0;
}

static size_t format_hpe_text_record(char *output, size_t output_capacity,
                                     const unsigned char *payload,
                                     size_t payload_length)
{
    static const char marker[] = "CSI record:\n";
    if (payload_length % sizeof(uint32_t) != 0)
        return 0;

    size_t word_count = payload_length / sizeof(uint32_t);
    size_t line_count = (word_count + CSI_HPE_WORDS_PER_LINE - 1)
                        / CSI_HPE_WORDS_PER_LINE;
    size_t required = sizeof(marker) - 1 + word_count * 11 + line_count;
    if (required > output_capacity)
        return 0;

    char *cursor = output;
    memcpy(cursor, marker, sizeof(marker) - 1);
    cursor += sizeof(marker) - 1;

    for (size_t word = 0; word < word_count; ++word) {
        size_t offset = word * sizeof(uint32_t);
        uint32_t value = (uint32_t)payload[offset]
                         | (uint32_t)payload[offset + 1] << 8
                         | (uint32_t)payload[offset + 2] << 16
                         | (uint32_t)payload[offset + 3] << 24;
        int written = snprintf(cursor, output_capacity - (size_t)(cursor - output),
                               "0x%08x\t", value);
        if (written != 11)
            return 0;
        cursor += written;
        if ((word + 1) % CSI_HPE_WORDS_PER_LINE == 0
            || word + 1 == word_count)
            *cursor++ = '\n';
    }

    return (size_t)(cursor - output);
}

static unsigned long parse_unsigned(const char *text, const char *name)
{
    char *end = NULL;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0') {
        fprintf(stderr, "Invalid %s: %s\n", name, text);
        exit(2);
    }
    return value;
}

int main(int argc, char **argv)
{
    int hpe_text = 0;
    int argument = 1;
    if (argc == 5 && strcmp(argv[1], "--hpe-text") == 0) {
        hpe_text = 1;
        argument = 2;
    } else if (argc != 4) {
        fprintf(stderr,
                "Usage: %s [--hpe-text] <netlink-id> <record-count> "
                "<output-file>\n"
                "  record-count 0 means run until SIGINT/SIGTERM\n"
                "  --hpe-text writes complete records using HPE CSI record "
                "text framing\n",
                argv[0]);
        return 2;
    }

    unsigned long netlink_id = parse_unsigned(argv[argument], "netlink ID");
    unsigned long requested_records = parse_unsigned(argv[argument + 1],
                                                      "record count");
    const char *output_path = argv[argument + 2];
    if (netlink_id > 511) {
        fprintf(stderr, "Netlink ID must be between 0 and 511\n");
        return 2;
    }

    int output_fd = open(output_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (output_fd < 0) {
        perror("open output");
        return 1;
    }

    int socket_fd = socket(AF_NETLINK, SOCK_RAW, (int)netlink_id);
    if (socket_fd < 0) {
        perror("netlink socket");
        close(output_fd);
        return 1;
    }

    int receive_buffer_bytes = 1024 * 1024;
    if (setsockopt(socket_fd, SOL_SOCKET, SO_RCVBUF,
                   &receive_buffer_bytes, sizeof(receive_buffer_bytes)) < 0)
        perror("warning: SO_RCVBUF");

    struct timeval receive_timeout = {
        .tv_sec = 1,
        .tv_usec = 0,
    };
    if (setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO,
                   &receive_timeout, sizeof(receive_timeout)) < 0)
        perror("warning: SO_RCVTIMEO");

    struct sockaddr_nl local = {
        .nl_family = AF_NETLINK,
        .nl_pid = (uint32_t)getpid(),
        .nl_groups = 2,
    };
    if (bind(socket_fd, (struct sockaddr *)&local, sizeof(local)) < 0) {
        perror("netlink bind");
        close(socket_fd);
        close(output_fd);
        return 1;
    }

    signal(SIGINT, request_stop);
    signal(SIGTERM, request_stop);

    unsigned long records = 0;
    unsigned long long payload_bytes = 0;
    unsigned long long output_bytes = 0;
    unsigned char buffer[CSI_NETLINK_MESSAGE_BYTES];
    char *hpe_text_buffer = NULL;
    if (hpe_text) {
        hpe_text_buffer = malloc(CSI_HPE_TEXT_RECORD_BYTES);
        if (!hpe_text_buffer) {
            fprintf(stderr, "Out of memory allocating HPE text buffer\n");
            close(socket_fd);
            close(output_fd);
            return 1;
        }
    }

    fprintf(stderr,
            "Listening on netlink %lu group 2; output=%s; target=%lu records; "
            "mode=%s\n",
            netlink_id, output_path, requested_records,
            hpe_text ? "hpe-text" : "binary");

    while (!stop_requested &&
           (requested_records == 0 || records < requested_records)) {
        memset(buffer, 0, sizeof(buffer));
        struct nlmsghdr *header = (struct nlmsghdr *)buffer;
        header->nlmsg_len = sizeof(buffer);
        header->nlmsg_pid = (uint32_t)getpid();

        struct sockaddr_nl source;
        memset(&source, 0, sizeof(source));
        struct iovec iov = {
            .iov_base = buffer,
            .iov_len = sizeof(buffer),
        };
        struct msghdr message = {
            .msg_name = &source,
            .msg_namelen = sizeof(source),
            .msg_iov = &iov,
            .msg_iovlen = 1,
        };

        ssize_t received = recvmsg(socket_fd, &message, 0);
        if (received < 0) {
            if (errno == EINTR)
                continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK)
                continue;
            perror("recvmsg");
            break;
        }
        if (received <= CSI_NETLINK_HEADER_BYTES) {
            fprintf(stderr, "Ignoring short netlink message: %zd bytes\n", received);
            continue;
        }

        size_t message_bytes = (size_t)received;
        if (header->nlmsg_len >= CSI_NETLINK_HEADER_BYTES &&
            header->nlmsg_len < message_bytes)
            message_bytes = header->nlmsg_len;

        size_t payload_length = message_bytes - CSI_NETLINK_HEADER_BYTES;
        const unsigned char *payload = buffer + CSI_NETLINK_HEADER_BYTES;
        const unsigned char *output_data = payload;
        size_t output_length = payload_length;
        if (hpe_text) {
            output_length = format_hpe_text_record(
                hpe_text_buffer, CSI_HPE_TEXT_RECORD_BYTES,
                payload, payload_length);
            output_data = (const unsigned char *)hpe_text_buffer;
            if (output_length == 0) {
                fprintf(stderr,
                        "Cannot format payload of %zu bytes as HPE text\n",
                        payload_length);
                break;
            }
        }
        if (write_all(output_fd, output_data, output_length) < 0) {
            perror("write output");
            break;
        }

        ++records;
        payload_bytes += payload_length;
        output_bytes += output_length;
        uint32_t format_id = 0;
        if (payload_length >= sizeof(format_id))
            memcpy(&format_id, payload, sizeof(format_id));
        /*
         * CSI can arrive from the driver in large bursts.  Printing one line
         * per record adds a synchronous write to the capture hot path and can
         * make the firmware's small CSI transfer ring overflow.  Keep enough
         * progress output for diagnostics without slowing every record.
         */
        if (records == 1 || records % 100 == 0 ||
            (requested_records != 0 && records == requested_records)) {
            fprintf(stderr,
                    "record=%lu netlink_bytes=%zd payload_bytes=%zu format_id=%u\n",
                    records, received, payload_length, format_id);
        }
    }

    if (fsync(output_fd) < 0)
        perror("warning: fsync");
    free(hpe_text_buffer);
    close(socket_fd);
    close(output_fd);

    fprintf(stderr,
            "Capture complete: records=%lu payload_bytes=%llu output_bytes=%llu "
            "mode=%s\n",
            records, payload_bytes, output_bytes,
            hpe_text ? "hpe-text" : "binary");
    return records == requested_records || requested_records == 0 ? 0 : 1;
}
