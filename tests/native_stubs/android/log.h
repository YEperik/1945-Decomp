#ifndef TEST_ANDROID_LOG_H
#define TEST_ANDROID_LOG_H
#define ANDROID_LOG_ERROR 6
int __android_log_print(int priority, const char *tag, const char *format, ...);
#endif
