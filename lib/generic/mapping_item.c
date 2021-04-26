void ITEM_INCREF(ITEM it)
{
	if (it.hash != 0) {
		KEY_INCREF(it.memb_key);
		VALUE_INCREF(it.memb_value);
	}
}

void ITEM_DECREF(ITEM it)
{
	if (it.hash != 0) {
		KEY_DECREF(it.memb_key);
		VALUE_DECREF(it.memb_value);
	}
}

bool ITEM_METHOD(equals)(ITEM a, ITEM b)
{
	return a.hash == b.hash && KEY_METHOD(equals)(a.memb_key, b.memb_key) && VALUE_METHOD(equals)(a.memb_value, b.memb_value);
}

struct String ITEM_METHOD(to_string)(ITEM it)
{
	struct String keystr = KEY_METHOD(to_string)(it.memb_key);
	struct String valstr = VALUE_METHOD(to_string)(it.memb_value);

	struct String res = cstr_to_string("MappingItem(");
	oomph_string_concat_inplace(&res, keystr);
	oomph_string_concat_inplace_cstr(&res, ": ");
	oomph_string_concat_inplace(&res, valstr);
	oomph_string_concat_inplace_cstr(&res, ")");

	decref_Str(keystr);
	decref_Str(valstr);
	return res;
}
