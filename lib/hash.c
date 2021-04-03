#include "oomph.h"
#include <stdio.h>
#include <openssl/evp.h>

// TODO: accept arbitrary binary data instead of utf-8 strings
struct class_Str *oomph_hash(const struct class_Str *data, const struct class_Str *algname)
{
	const EVP_MD *alg = EVP_get_digestbyname(algname->str);
	if (!alg)
		panic_printf("unknown hash algorithm name: %s", algname->str);

	unsigned nbytes;
	unsigned char hash[EVP_MAX_MD_SIZE];

	EVP_MD_CTX *ctx = EVP_MD_CTX_new();
	if (!ctx)
		panic_printf("EVP_MD_CTX_new failed");
	if (!EVP_DigestInit(ctx, alg))
		panic_printf("EVP_DigestInit failed");
	if (!EVP_DigestUpdate(ctx, data->str, strlen(data->str)))
		panic_printf("EVP_DigestUpdate failed");
	if (!EVP_DigestFinal(ctx, hash, &nbytes))
		panic_printf("EVP_DigestFinal failed");
	EVP_MD_CTX_free(ctx);

	char hex[2*EVP_MAX_MD_SIZE + 1];
	for (unsigned i = 0; i < nbytes; i++)
		sprintf(hex + 2*i, "%02x", hash[i]);
	return cstr_to_string(hex);
}
