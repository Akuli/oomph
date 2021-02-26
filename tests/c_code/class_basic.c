struct class_Point {
	REFCOUNT_HEADER
	int64_t memb_x;
	int64_t memb_y;
	
};
struct class_Point *ctor_Point(int64_t var_x,int64_t var_y) {
	struct class_Point *obj = malloc(sizeof(*obj));
	obj->refcount = 1;
	obj->memb_x = var_x;
	obj->memb_y = var_y;
	return obj;
}
void var_print_point(struct class_Point *var_p){
	(var_print_int(((var_p)->memb_x)));
	(var_print_int(((var_p)->memb_y)));
	out:
	(void)0;
}
void var_main(void){
	void *ref0 = NULL;
	void *ref1 = NULL;
	void *ref2 = NULL;
	decref((ctor_Point(((int64_t)1LL),((int64_t)2LL))));
	struct class_Point *var_p = (ref1 = (ctor_Point(((int64_t)123LL),((int64_t)456LL))));
	(var_print_point(var_p));
	(var_print_point((ref2 = (ctor_Point(((int64_t)111LL),((int64_t)222LL))))));
	out:
	if (ref2) decref(ref2);
	if (ref1) decref(ref1);
	if (ref0) decref(ref0);
	(void)0;
}
